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
import subprocess
from pathlib import Path
try:
    from gooey import Gooey, GooeyParser #Create GUI from cmd-line app
    gooey_present = True
except:
    gooey_present = False

class TemplateError(Exception):
    pass

_CONTENT_PATTERN = re.compile(r"(?<!\\)%[^%]*(?<!\\)%")
_FILENAME_PATTERN = re.compile(r"(?<!\^)%[^%]*(?<!\^)%")

_SETTINGS_FILE_NAME = ".template_settings.toml"

def _paths_to_posix(value):
    if isinstance(value, Path):
        value = value.absolute().as_posix()
    return value

def _create_settings_file(project_path: Path, args):
    d = vars(args)
    d = {key: str(_paths_to_posix(val)) for key, val in d.items()}
    with open(project_path / _SETTINGS_FILE_NAME, 'x') as f:
        toml.dump(d, f)


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


""" GIT WRAPPER FUNCTIONS """
def _git_check_out_commit(local_repo, commit):
    result = subprocess.run(['git', '-C', local_repo, 'checkout', commit, '--detach'], capture_output=True)            
    if result.returncode != 0:
        raise TemplateError(f'Could not check out commit "{commit}".\nGit output:\n{result.stderr.decode()}')

def _git_clone(repo, newdir):
    result = subprocess.run(['git', 'clone', repo, newdir], capture_output=True)
    if result.returncode != 0:
        raise TemplateError(f'Could not clone git repo "{repo}".\nGit output:\n{result.stderr.decode()}')

def _get_current_commit_hash(local_repo):
    result = subprocess.run(['git', '-C', local_repo,  'rev-parse', '--short', 'HEAD'], capture_output=True)
    if result.returncode == 0:
        return result.stdout.decode()[0:7]
    return ''

def _has_local_changes(local_repo):
    result = subprocess.run(['git', '-C', local_repo, 'status', '--porcelain'], capture_output=True)
    if result.returncode == 0 and result.stdout == b'':
        return False
    return True

def _get_git_origin(local_repo):
    result = subprocess.run(['git', '-C', local_repo, 'remote', 'get-url', 'origin'], capture_output=True)
    if result.returncode == 0 and result.stdout != b'':
        return result.stdout.decode()[0:-1]
    return None

def _git_hash_exists_on_origin(local_repo, hash):
    subprocess.run(['git', '-C', local_repo, 'fetch'])
    result = subprocess.run(['git', '-C', local_repo, 'branch', '-r', '--contains', hash], capture_output=True)
    if result.returncode != 0 or result.stdout == b'':
        return False
    return True

def _is_git_repo(local_repo):
    result = subprocess.run(['git', '-C', local_repo, 'rev-parse'])
    return result.returncode == 0

""" END GIT WRAPPER FUNCTIONS """

def _clone_and_check_out(args, tempdir):    
    _git_clone(args.git_repo, tempdir)                                    
    if args.git_commit:        
        _git_check_out_commit(tempdir, args.git_commit)
    else:
        args.git_commit = _get_current_commit_hash(tempdir)
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
    if output_path.exists():
        return output_path / project_name
    return output_path

def _check_is_local_source_git_repo(args):
    if args.template_path:
        if _is_git_repo(args.template_path):
            if not _has_local_changes(args.template_path):
                args.git_commit = _get_current_commit_hash(args.template_path)
                args.git_repo = args.template_path
                remote = _get_git_origin(args.template_path)
                if remote and _git_hash_exists_on_origin(args.template_path, args.git_commit):
                    args.git_repo = remote
            else:
                print("Warning: template folder is a git repository, but has uncommitted changes. You may not be able to recreate this template or update the project at a later time.")

def _check_is_git_repo_local(args):
    if args.git_repo and Path(args.git_repo).exists():
        args.git_repo = Path(args.git_repo)

def _get_arguments_from_toml(tomlfilepath, args):
    tomlargs = toml.load(tomlfilepath)
    if "git_repo" in tomlargs and tomlargs["git_repo"] != 'None':
        tomlargs["template_path"] = None
    for key, val in tomlargs.items():
        if not hasattr(args, key) or not getattr(args, key):
            if val == 'None':
                val = None
            if key.endswith("path") and val:
                val = Path(val)
            setattr(args, key, val)
    return args

def main(args):
    if args.settings_toml:
        args = _get_arguments_from_toml(args.settings_toml, args)
    
    _check_arguments(args)        #Raises an exception if invalid arguments

    if args.git_repo:
        tempdir = tempfile.TemporaryDirectory()    
        args.template_path = _clone_and_check_out(args, tempdir.name)
    else:
        _check_is_local_source_git_repo(args)

    _check_is_git_repo_local(args)

    # Find all variables to be replaced in the template
    files = _list_of_files(args.template_path)
    required_vars = _find_required_vars(files)
    
    _add_free_vars_to_args(args)
    
    _exception_if_required_args_are_not_present(args, required_vars)    

    args.output_path = _new_path_if_already_exists(args.output_path, args.project)

    _replace_filenames(files, args, args.output_path, args.template_path)

    newfiles = _list_of_files(args.output_path)

    for file in newfiles:
        if not Path(file).is_dir():
            _replace_file_contents(file, args)

    _create_settings_file(args.output_path, args)

def _parse_command_line_arguments(argv):
    program_name = "Create project from template"
    description = "Use this program to generate a new project from a template."
    dirchooser = {}
    filechooser = {}
    if gooey_present:
        #GooeyParser extends argparse.ArgumentParser. You can still use this as a command line parser, but it takes the additional "widget" argument for use in the GUI
        ap = GooeyParser(prog=program_name,description=description)
        dirchooser = {'widget':'DirChooser'}
        filechooser = {'widget' : 'FileChooser'}
    else:
        ap = argparse.ArgumentParser(prog=program_name,description=description)    
        
    if not "--settings-toml" in argv:
        ap.add_argument("project",  help="Name of the new project")    
        ap.add_argument("output_path", type=Path, help="Path to new project to be created", **dirchooser)
    else:
        ap.add_argument("--project",  help="Name of the new project")    
        ap.add_argument("--output-path", type=Path, help="Path to new project to be created", **dirchooser)
    ap.add_argument("--template-path",  type=Path, help="Path to folder containing template to create project from", **dirchooser)
    ap.add_argument("--description", help="Description of the project")
    ap.add_argument("--author", help = "Name of the author of the project")
    ap.add_argument("--email", help = "E-mail of the author of the project")
    ap.add_argument("--variables", type=str, nargs="*", help="Other variables used for replacing values in the template. List in the form 'KEYWORD1:VALUE1 KEYWORD2:VALUE2 keyWord3:Value3'")
    ap.add_argument("--git-repo", help = "Git repository link to template (either git://<repo_url>.git, http://<repo_url>.git or <path_to_local_repo>)")
    ap.add_argument("--git-commit", help="Commit hash if not creating from the head of the default git branch")
    ap.add_argument("--git-folder", help="Folder under the git repo where the template is located. Default is '.'")
    ap.add_argument("--settings-toml", type=Path, help = "Path to .template-settings.toml file to use as settings for the project", **filechooser)

    args = ap.parse_args(argv)

    return args

def _check_arguments(args): 
    """
    Raises an exception if invalid arguments
    """
    if not (bool(args.template_path) != bool(args.git_repo)):
        raise TemplateError("Either template path or git repo must be provided, but not both")
    if args.template_path and not args.template_path.exists():
        raise TemplateError(f"Template folder '{args.template_path}' not found")    

def entry_point():
    args = _parse_command_line_arguments(sys.argv[1:])
    try:
        main(args)
    except TemplateError as e:
        print(e)
        sys.exit(1)

    print(f"New project created successfully in directory {args.output_path}")


if gooey_present:
    @Gooey(required_cols=1, 
           default_size=(500, 780),
            program_name="Create project from template",
            target="template-gui")    
    def entry_point_gui(): #Separate entry point for the GUI
        entry_point()
else:
    def entry_point_gui():
        print("Gooey is required to run the GUI. Type \"pip install gooey\" to install it")
        sys.exit(1)

if __name__ == "__main__":
    entry_point()

