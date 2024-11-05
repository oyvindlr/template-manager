import sys
import shutil
import os
import glob
import os.path
import re
import argparse
import toml
import tempfile
import shutil
import datetime
import platform
from template_generator import git_wrapper as git
from template_generator import create_gitlab_project
from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
try:
    from gooey import Gooey, GooeyParser #Create GUI from cmd-line app
    gooey_present = True
except:
    gooey_present = False

running_in_gui = False

class TemplateError(Exception):
    pass

_CONTENT_PATTERN = re.compile(r"(?<!\\)%[^%]*(?<!\\)%")
_FILENAME_PATTERN = re.compile(r"(?<!\^)%[^%]*(?<!\^)%")

_PROJECT_SETTINGS_FILE_NAME = ".template_settings.toml"

_GENERAL_SETTINGS_FILE = Path(__file__).parent / "settings.toml"



def _project_settings(args):
    d = vars(args)
    #d = {key: str(_paths_to_posix(val)) for key, val in d.items()}
    d = {key: str(val) for key, val in d.items()}
    d["template"] = d["git_repo"] if "git_repo" in d and d["git_repo"] else d["template_path"]
    d.pop("git_repo", None)
    d.pop("template_path", None)
    d.pop("tempdir", None)
    d.pop("output_path", None)
    d.pop("settings_toml", None)
    return d

def _create_settings_file(project_path: Path, args):
    d = _project_settings(args)
    with open(project_path / _PROJECT_SETTINGS_FILE_NAME, 'x') as f:
        toml.dump(d, f)

def _read_settings():    
    d =  {"default_template_repo":None, "email":None, "author":None}
    try:
        d.update(toml.load(_GENERAL_SETTINGS_FILE))
    except:
        pass
    return d

def _find_vars_in_file_names(filelist:list[Path]) -> set:
    vars_ = []
    for file in filelist:
        vars_.extend(re.findall(_FILENAME_PATTERN, str(file)))
    vars_ = [var.strip('%') for var in vars_]
    return set(vars_)

def _find_vars_in_file(filename):
    with open(filename) as f:
        try:
            content = f.read()
            vars_ = re.findall(_CONTENT_PATTERN, content)
            vars_ = [var.strip('%') for var in vars_]
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
            namevalue = var_.split(":")        
            setattr(args, namevalue[0], namevalue[1])



def _clone_and_check_out(args, tempdir):    
    git.clone(args.git_repo, tempdir)                                    
    if args.git_commit:        
        git.check_out_commit(tempdir, args.git_commit)
    else:
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

def _replace_filenames(files, vars, outdir: Path, files_basedir):        
    for file in files:
        filepath = Path(file)
        relfile = filepath.relative_to(files_basedir)        
        newfile = _replace_variables(str(relfile), vars, _FILENAME_PATTERN)
        newfile = _unescape_filename(newfile)
        newfilepath = outdir / newfile        
        if not filepath.is_dir():
            Path(os.path.dirname(newfilepath)).mkdir(parents = True, exist_ok = True)
            shutil.copy(filepath, newfilepath)
        else:
            Path(newfilepath).mkdir(parents = True, exist_ok = True) #os.path.dirname cannot figure out if dir or file if path doesn't already exist)
        

def _replace_file_contents(file, vars):
    try:
        content = Path(file).read_text()
    except UnicodeDecodeError:
        return #Binary file, just ignore
    newcontent = _replace_variables(content, vars, _CONTENT_PATTERN)
    newcontent = _unescape_content(newcontent)
    if newcontent != content:
        Path(file).write_text(newcontent)

def _new_path_if_already_exists(output_path:Path, project_name:str):
    if output_path == None:
        return Path(project_name)
    elif output_path.exists():
        return output_path / project_name
    return output_path

def _check_is_local_source_git_repo(args):
    if git.dir_contains_repo(args.template):
        if not git.has_local_changes(args.template):
            args.git_commit = git.get_current_commit_hash(args.template)
            args.git_repo = args.template
            remote = git.get_origin(args.template)
            if remote and git.hash_exists_on_origin(args.template, args.git_commit):
                args.git_repo = remote
        else:
            print("Warning: template folder is a git repository, but has uncommitted changes. You may not be able to recreate this template or update the project at a later time.")


def _get_arguments_from_toml(tomlfilepath, args):
    tomlargs = toml.load(tomlfilepath)
    if "git_repo" in tomlargs and tomlargs["git_repo"] != 'None':
        tomlargs["template"] = "git_repo"
    for key, val in tomlargs.items():
        if val == 'None':
            val = None
        setattr(args, key, val)
    return args

def _find_template_source(args):
    if args.template.endswith(".git") or args.git_commit: #If local folder, but git commit given, also treat as repo
        args.git_repo = args.template
        tempdir = tempfile.TemporaryDirectory()    
        args.template_path = _clone_and_check_out(args, tempdir.name)
        args.tempdir = tempdir #Bit of a hack; tempdir may be deleted when out of context, so keep it by adding it to the args structure
    elif Path(args.template).exists():
        args.template_path = Path(args.template)
        _check_is_local_source_git_repo(args)
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
    if platform.system() == "Windows":
        os.startfile(_GENERAL_SETTINGS_FILE)
    elif platform.system() == "Linux":
        os.system(f"nano {_GENERAL_SETTINGS_FILE}")
    elif platform.system() == "Darwin":
        os.system(f"open {_GENERAL_SETTINGS_FILE}")
    else:
        print(f"Error: Unknown platform {platform.system()}")


def _build(args):
    if hasattr(args, "settings_toml") and args.settings_toml:
        args = _get_arguments_from_toml(args.settings_toml, args)

    _check_arguments(args)        #Raises an exception if invalid arguments

    _add_special_variables(args)

    _find_template_source(args)

    # Find all variables to be replaced in the template
    files = _list_of_files(args.template_path)
    required_vars = _find_required_vars(files)
    
    _add_free_vars_to_args(args)
    
    _exception_if_required_args_are_not_present(args, required_vars)    

    args.output_path = _new_path_if_already_exists(args.output_path, args.project_folder)

    _replace_filenames(files, args, args.output_path, args.template_path)

    newfiles = _list_of_files(args.output_path)

    for file in newfiles:
        if not Path(file).is_dir():
            _replace_file_contents(file, args)


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
    ap.add_argument("--variables", type=str, nargs="*", help="Other variables used for replacing values in the template. List in the form 'KEYWORD1:VALUE1 KEYWORD2:VALUE2 keyWord3:Value3'")
    ap.add_argument("--git-commit", help="Commit hash if not creating from the head of the default git branch")
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
        args.version = version("template_generator")
    except:
        try:
            import template_generator
            args.version = template_generator.__version__
        except:
            args.version = "0.0.0"


    return args

def  _add_special_variables(args):
    args.project_folder = args.project.replace(" ", "_")
    args.project_us = args.project_folder.replace("-", "_")
    args.project_lc = args.project.replace(" ", "-").lower()
    args.project_us_lc = args.project_us.lower()
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
            args.gitlab_group = input("If you want to create a gitlab project, enter the group name. Otherwise hit enter to exit. You can create a gitlab project later by running 'gitlab-create --path "+str(output_path)+"'\n")
        if args.gitlab_group:
            create_gitlab_project.main(["--path", str(output_path), "--group", args.gitlab_group])
    return output_path



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

