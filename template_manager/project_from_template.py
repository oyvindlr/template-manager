from __future__ import annotations
import sys
import shutil
import os
import os.path
import re
import argparse
import toml
import tempfile
import shutil
import datetime
import platform
import uuid
from template_manager import git_wrapper as git
from template_manager import create_gitlab_project
from platformdirs import user_config_dir
from importlib.metadata import version
from .strip import strip_ifs_and_elses
from pathlib import Path
from jinja2 import StrictUndefined, TemplateError as JinjaTemplateError
from jinja2.sandbox import SandboxedEnvironment
try:
    from gooey import Gooey, GooeyParser #Create GUI from cmd-line app
    gooey_present = True
except:
    gooey_present = False

running_in_gui = False

class TemplateError(Exception):
    pass

# Jinja block delimiters are literal when legacy syntax is explicitly selected.
_CONTENT_PATTERN = re.compile(r"(?<![\\{])%(?!})[^%]*(?<!\\)%(?!})")
_FILENAME_PATTERN = re.compile(r"(?<![\^{])%(?!})[^%]*(?<!\^)%(?!})")
_UUID_PATTERN = re.compile(r"uuid\[([^\[\]\r\n]+)\]")
_COOKIECUTTER_PATTERN = re.compile(r"{{.*?}}|{%.*?%}", re.DOTALL)


class _ConditionalUndefined(StrictUndefined):
    # Optional flags may be absent, but printing a missing variable is an error.
    def __bool__(self):
        return False


_JINJA_ENVIRONMENT = SandboxedEnvironment(
    undefined=_ConditionalUndefined, keep_trailing_newline=True, autoescape=False,
)


def _render_cookiecutter(content, args):
    context = vars(args).copy()
    context["cookiecutter"] = vars(args).copy()
    try:
        return _JINJA_ENVIRONMENT.from_string(content).render(context)
    except JinjaTemplateError as error:
        raise TemplateError(f"Invalid Cookiecutter template: {error}") from error


def _uses_cookiecutter(args):
    return getattr(args, "_resolved_template_syntax", getattr(args, "template_syntax", None)) == "cookiecutter"


def _detect_template_syntax(files, basedir):
    """Prefer Jinja markers in relative paths or text; otherwise use legacy."""
    for file in files:
        path = Path(file)
        if _COOKIECUTTER_PATTERN.search(str(path.relative_to(basedir))):
            return "cookiecutter"
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                continue
            if _COOKIECUTTER_PATTERN.search(content):
                return "cookiecutter"
    return "legacy"

_PROJECT_SETTINGS_FILE_NAME = ".template_settings.toml"

_GENERAL_SETTINGS_FILE = Path(__file__).parent / "settings.toml"

def _paths_to_posix(var):
    if isinstance(var, Path):
        return var.as_posix()
    return var

def _project_settings(args):
    d = vars(args)
    d = {key: str(_paths_to_posix(val)) for key, val in d.items()}
    #d = {key: str(val) for key, val in d.items()}
    d["template"] = d["git_repo"] if "git_repo" in d and d["git_repo"] else d["template_path"]
    d.pop("git_repo", None)
    d.pop("template_path", None)
    d.pop("tempdir", None)
    d.pop("output_path", None)
    d.pop("settings_toml", None)
    d.pop("variables", None)
    d.pop("_resolved_template_syntax", None)
    return d

def _create_settings_file(project_path: Path, args):
    d = _project_settings(args)
    with open(project_path / _PROJECT_SETTINGS_FILE_NAME, 'x', encoding='utf-8') as f:
        toml.dump(d, f)

def _get_general_settings_path():
    config_dir = user_config_dir("template-manager")
    config_path = os.path.join(config_dir, "settings.toml")

    # Ensure the config directory exists
    os.makedirs(config_dir, exist_ok=True)

    # Copy the default config if it doesn't exist
    if not os.path.exists(config_path):
        default_config = _GENERAL_SETTINGS_FILE.read_text()
        with open(config_path, "w") as config_file:
            config_file.write(default_config)
    return Path(config_path)

def _read_settings():    
    d =  {"default_template_repo":None, "email":None, "author":None}
    toml_path = _get_general_settings_path()
    try:
        d.update(toml.load(toml_path))
    except:
        pass
    return d

def _find_vars_in_file_names(filelist:list[Path]) -> set:
    vars_ = []
    for file in filelist:
        vars_.extend(re.findall(_FILENAME_PATTERN, str(file)))
    vars_ = [var.strip('%') for var in vars_]
    return set(vars_)

def remove_if_and_else(vars_):
    for var in vars_.copy():
        if var.startswith("if(") or var.startswith("elseif(") or var == "else" or var == "endif":
            vars_.remove(var)

def _find_vars_in_file(filename):
    with open(filename, encoding="utf-8-sig") as f:
        try:
            content = f.read()
            vars_ = re.findall(_CONTENT_PATTERN, content)
            vars_ = [var.strip('%') for var in vars_]
            remove_if_and_else(vars_) #Variables that are only used in if() and elseif() statements are not required
            vars_ = set(vars_)
        except UnicodeDecodeError:
            vars_ = set() #Binary file, just ignore
    return vars_

def _find_required_vars(files):
    all_vars = _find_vars_in_file_names(files)
    for file in files:
        if not file.is_dir():
            file_vars = _find_vars_in_file(file)
            all_vars = all_vars.union(file_vars)
    return all_vars

def _list_of_files(dir):
    """
    Return list of all files in directory and subdirectories, 
    excluding any files found in ".git" directories
    """
    filelist = []
    for root, dirs, files in os.walk(dir):
        filelist.extend([Path(root)/file for file in files])
        if ".git" in dirs:
            dirs.remove(".git")
    return filelist

def _unescape_content(string:str):
    return string.replace(r"\%", "%")

def _unescape_filename(string:str):
    return string.replace(r"^%", "%")

    
def _add_free_vars_to_args(args):
    """
    Add the command-line input keyword:value pairs to the arguments structure
    """
    if args.variables:
        free_vars = args.variables
        del(args.variables)
        for var_ in free_vars:
            name, value = var_.split(":", maxsplit=1)
            if len(value) >= 2 and value[0] == value[-1] == "'":
                value = value[1:-1]
            setattr(args, name, value)



def _clone_and_check_out(args, tempdir):    
    git.clone(args.git_repo, tempdir)
    if not hasattr(args, 'git_branch'):
        args.git_branch = ""
    item = args.git_commit            
    if args.git_branch and not args.git_commit: #If branch given, but not commit, check out branch
        item = args.git_branch
    if item:        
        git.check_out(tempdir, item)
        if git.is_branch(tempdir,item):
            args.git_branch = item    
    args.git_commit = git.get_current_commit_hash(tempdir)
    if not args.git_folder:
        args.git_folder = "."
    return Path(tempdir) / args.git_folder

             


def _exception_if_required_args_are_not_present(args, required_vars):
    for varname in required_vars:
        if not hasattr(args, varname) or not getattr(args, varname):
            raise TemplateError(f'The variable "{varname}" is necessary for this template, but is not defined in the command line arguments')

def _replace_variables(string, vars, pattern):
    return re.sub(pattern, lambda x:getattr(vars, x.group().strip('%')), string)


def _replace_uuids(string, args, uuid_values):
    def replace(match):
        name = match.group(1)
        if name not in uuid_values:
            namespace = uuid.uuid5(uuid.NAMESPACE_URL, args.uuid_seed)
            uuid_values[name] = str(uuid.uuid5(namespace, name))
        return uuid_values[name]

    return _UUID_PATTERN.sub(replace, string)


def _replace_filenames(files, vars, outdir: Path, files_basedir, uuid_values=None):
    if uuid_values is None:
        uuid_values = {}
    outdir.mkdir(parents=True, exist_ok=True)
    output_root = outdir.resolve()
    for file in files:
        filepath = Path(file)
        relfile = filepath.relative_to(files_basedir)        
        if _uses_cookiecutter(vars):
            # An excluded directory excludes its descendants too. Stop before
            # rendering descendant names, which may refer to missing variables.
            components = []
            for component in relfile.parts:
                rendered = _render_cookiecutter(component, vars)
                if not rendered:
                    break
                if Path(rendered).is_absolute():
                    raise TemplateError(f"Rendered path is absolute: {relfile}")
                components.append(rendered)
            else:
                newfile = str(Path(*components))
            if len(components) != len(relfile.parts):
                continue
        else:
            newfile = _replace_variables(str(relfile), vars, _FILENAME_PATTERN)
            newfile = _unescape_filename(newfile)
        newfile = _replace_uuids(newfile, vars, uuid_values)
        newfilepath = outdir / newfile        
        if Path(newfile).is_absolute():
            raise TemplateError(f"Rendered path is absolute: {relfile}")
        resolved = newfilepath.resolve()
        if resolved == output_root or not resolved.is_relative_to(output_root):
            raise TemplateError(f"Rendered path escapes the output directory: {relfile}")
        if not filepath.is_dir():
            Path(os.path.dirname(newfilepath)).mkdir(parents = True, exist_ok = True)
            shutil.copy(filepath, newfilepath)
        else:
            Path(newfilepath).mkdir(parents = True, exist_ok = True) #os.path.dirname cannot figure out if dir or file if path doesn't already exist)
        

def _replace_file_contents(file, vars, uuid_values=None):
    if uuid_values is None:
        uuid_values = {}
    try:
        content = Path(file).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return #Binary file, just ignore
    if _uses_cookiecutter(vars):
        newcontent = _render_cookiecutter(content, vars)
    else:
        newcontent = strip_ifs_and_elses(content, __builtins__["vars"](vars))
        newcontent = _replace_variables(newcontent, vars, _CONTENT_PATTERN)
        newcontent = _unescape_content(newcontent)
    newcontent = _replace_uuids(newcontent, vars, uuid_values)
    if newcontent != content:
        Path(file).write_text(newcontent, encoding="utf-8")

def _new_path_if_already_exists(output_path:Path, project_name:str):
    if output_path == None:
        return Path(project_name)
    elif output_path.exists() and output_path.name != project_name:
        return output_path / project_name
    return output_path

def _get_repo(args):
    if args.template.endswith(".git"):#Presumably remote repo
        return args.template
    if git.dir_contains_repo(args.template):#Local repo
        if not git.has_local_changes(args.template):
            remote = git.get_origin(args.template)
            hash = args.git_commit if args.git_commit else git.get_current_commit_hash(args.template)
            if remote and git.hash_exists_on_origin(args.template, hash):
                return remote
            return args.template
        else:
            print("Warning: template folder is a git repository, but has uncommitted changes. You may not be able to recreate this template or update the project at a later time.")        
            return ""
    return ""

    

def _get_arguments_from_toml(tomlfilepath, args):
    tomlargs = toml.load(tomlfilepath)
    if "git_repo" in tomlargs and tomlargs["git_repo"] != 'None':
        tomlargs["template"] = "git_repo"    
    tomlargs.pop("variables", None) #Individual vars are defined in the toml, so we dont need the "variables" field. We used to not remove the "variables" during project creation, so now we need to disregard it here
    for key, val in tomlargs.items():
        if val == 'None':
            val = None
        setattr(args, key, val)
    return args

def _find_template_source(args):
    args.git_repo = _get_repo(args)
    if args.git_repo:        
        tempdir = tempfile.TemporaryDirectory()    
        args.template_path = _clone_and_check_out(args, tempdir.name)
        args.tempdir = tempdir #Bit of a hack; tempdir may be deleted when out of context, so keep it by adding it to the args structure
    elif Path(args.template).exists():
        args.template_path = Path(args.template)
    else:
        raise TemplateError(f"Provided template source {args.template} is not a git repository or local directory")
    
def _folder_list(template_repo):
    temp_dir = tempfile.TemporaryDirectory()
    git.clone(template_repo, temp_dir.name, "--depth", "1")
    items = os.listdir(temp_dir.name)
    flist = []
    for item in items:
        if item != ".git":
            if (Path(temp_dir.name) / item) .is_dir():
                flist.append(item)
    return flist

def _folder_list_from_argv(argv, defaults):
    template = None
    if "default_template_repo" in defaults:
        template = defaults["default_template_repo"]
    if "--template" in argv:
        template = argv[argv.index("--template") + 1]
    if template:
        return _folder_list(template)
    return []

def _list_folders(args):
    if not args.template:
        print("No template repository provided. Use --template or define a default repository using --edit-settings")
        return
    folders = _folder_list(args.template)
    for folder in folders:
        print(folder)

def _edit_settings():
    settings_file = _get_general_settings_path()
    if platform.system() == "Windows":
        os.startfile(settings_file)
    elif platform.system() == "Linux":
        os.system(f"nano {settings_file}")
    elif platform.system() == "Darwin":
        os.system(f"open {settings_file}")
    else:
        print(f"Error: Unknown platform {platform.system()}")


def _build(args):
    requested_syntax = getattr(args, "template_syntax", None)
    if hasattr(args, "settings_toml") and args.settings_toml:
        args = _get_arguments_from_toml(args.settings_toml, args)
        if requested_syntax in ("legacy", "cookiecutter"):
            args.template_syntax = requested_syntax

    _check_arguments(args)        #Raises an exception if invalid arguments

    _add_special_variables(args)

    _find_template_source(args)

    # Find all variables to be replaced in the template
    files = _list_of_files(args.template_path)
    args.template_syntax = getattr(args, "template_syntax", None) or "auto"
    if args.template_syntax not in ("auto", "legacy", "cookiecutter"):
        raise TemplateError(f"Unknown template syntax: {args.template_syntax}")
    args._resolved_template_syntax = (
        _detect_template_syntax(files, args.template_path)
        if args.template_syntax == "auto" else args.template_syntax
    )
    
    _add_free_vars_to_args(args)

    if not getattr(args, "uuid_seed", None):
        args.uuid_seed = str(uuid.uuid4())
    
    # Jinja checks missing variables during rendering, after selecting branches.
    if not _uses_cookiecutter(args):
        required_vars = _find_required_vars(files)
        _exception_if_required_args_are_not_present(args, required_vars)

    args.output_path = _new_path_if_already_exists(args.output_path, args.project_folder)

    uuid_values = {}
    _replace_filenames(files, args, args.output_path, args.template_path, uuid_values)

    newfiles = _list_of_files(args.output_path)

    for file in newfiles:
        if not Path(file).is_dir():
            _replace_file_contents(file, args, uuid_values)


    _create_settings_file(args.output_path, args)

    return args.output_path

def _parse_command_line_arguments(argv, defaults):
    program_name = "Create project from template"
    description = "Use this program to generate a new project from a template."
    dirchooser = {}
    filechooser = {}
    folder_choices = {}
    if running_in_gui:
        #GooeyParser extends argparse.ArgumentParser. You can still use this as a command line parser, but it takes the additional "widget" argument for use in the GUI
        ap = GooeyParser(prog=program_name,description=description)
        dirchooser = {'widget':'DirChooser'}
        filechooser = {'widget' : 'FileChooser'}
        folder_choices = {'choices': [".", *_folder_list_from_argv(argv, defaults)] }
    else:
        ap = argparse.ArgumentParser(prog=program_name,description=description)    
        
    if not "--settings-toml" in argv and not "-t" in argv and not "--edit-settings" in argv and not "--list-folders" in argv: 
        ap.add_argument("project",  help="Name of the new project")
    ap.add_argument("--template", help="Location of the template, either a directory or a git repository", default= defaults["default_template_repo"],**dirchooser) 
    ap.add_argument("-o", "--output-path", type=Path, help="Path to new project to be created. Default is ./<project name>", **dirchooser)
    ap.add_argument("-d","--description", help="Description of the project")
    ap.add_argument("--author", help = "Name of the author of the project", default = defaults["author"])
    ap.add_argument("--email", help = "E-mail of the author of the project", default = defaults["email"])
    ap.add_argument("--uuid-seed", help="Seed for uuid[name] placeholders. Generated randomly if omitted and saved in .template_settings.toml for recreation and updates.")
    ap.add_argument("--variables", type=str, nargs="*", help="Other variables used for replacing values in the template. List in the form 'KEYWORD1:VALUE1 KEYWORD2:VALUE2 keyWord3:Value3'")
    syntax = ap.add_mutually_exclusive_group()
    syntax.add_argument("--cookiecutter-syntax", dest="template_syntax", action="store_const", const="cookiecutter",
                        help="Render {{ variables }} and {%% if ... %%} blocks using Jinja")
    syntax.add_argument("--legacy-syntax", dest="template_syntax", action="store_const", const="legacy",
                        help="Render %%variables%% and %%if(...)%% blocks (default: autodetect syntax)")
    ap.add_argument("--git-commit", help="Commit hash, tag or branch. Defaults to the main branch.")
    ap.add_argument("--git-folder", help="Folder under the git repo where the template is located. Default is '.'", **folder_choices)  
    ap.add_argument("--gitlab-group", help="The group in GitLab to place the project under. If given, a gitlab project will be created in that group.", type=str, default=None)    
    if not running_in_gui:        
        ap.add_argument("-t","--settings-toml", type=Path, help = "Path to .template-settings.toml file to use as settings for the project", **filechooser)
        ap.add_argument("--edit-settings", help= "Edit settings such as default template repo and author details", action='store_true')
        ap.add_argument("--list-folders", help="Output a list of folders in the root of the git repository", action='store_true')
        ap.add_argument("--no-gitlab-project", help="Only create template, no gitlab project", action='store_true', default=False)

    args = ap.parse_args(argv)

    #Version argument only relevant when recreating project using toml file. May be used for forward compatibility, to generate templates and toml files as they would be
    #generated using that specific version of this program
    try:
        args.version = version("template_manager")
    except:
        try:
            import template_manager
            args.version = template_manager.__version__
        except:
            args.version = "0.0.0"


    return args

def  _add_special_variables(args):
    args.project_folder = args.project.replace(" ", "_")
    args.project_us = args.project_folder.replace("-", "_")    
    args.project_lc = args.project.replace(" ", "-").lower()
    args.project_kebab = args.project_lc
    args.project_us_lc = args.project_us.lower()
    args.project_snake = args.project_us_lc
    args.PROJECT_UPPER = args.project_us.upper()
    args.ProjectPascal = "".join(word.capitalize() for word in args.project_us.split("_"))
    args.projectCamel = args.ProjectPascal[0].lower() + args.ProjectPascal[1:]
    args.date = datetime.datetime.now().date().isoformat()

def _check_arguments(args): 
    """
    Raises an exception if invalid arguments
    """
    pass

def main(argv):
    defaults = _read_settings()
    args = _parse_command_line_arguments(argv, defaults)
    if hasattr(args, "edit_settings") and args.edit_settings:
        _edit_settings()
        sys.exit(0)
    if hasattr(args, "list_folders") and args.list_folders:
        _list_folders(args)
        sys.exit(0)
    try:
        output_path = _build(args)
    except TemplateError as e:
        print(e)
        sys.exit(1)

    print(f"New project created successfully in directory {args.output_path}")
    if not hasattr(args, "no_gitlab_project") or not args.no_gitlab_project:
        if not running_in_gui and not args.gitlab_group:
            args.gitlab_group = input("If you want to create a gitlab project, enter the group name. Otherwise hit enter to exit. You can create a gitlab project later by running 'gitlab-new --path "+str(output_path)+"'\n")
        if args.gitlab_group:
            create_gitlab_project.main(["--path", str(output_path), "--group", args.gitlab_group])
    return output_path


def template_gen_gen():
    """
    Geir's special function so he can remember how to use the template manager    
    """
    print('template-gen "My project" -o "temp" --description "My description" --author "Geirr" --email geni@naxystech.com --git-folder python_project_simple_ci')


def entry_point():
    main(sys.argv[1:])



if gooey_present:
    @Gooey( 
           default_size=(500, 920),
            program_name="Create project from template",
            target="template-gui")
    def entry_point_gui(): #Separate entry point for the GUI
        global running_in_gui
        running_in_gui = True
        entry_point()
else:
    def entry_point_gui():
        print("Gooey is required to run the GUI. Type \"pip install gooey\" to install it")
        sys.exit(1)

if __name__ == "__main__":
    entry_point()

