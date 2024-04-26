import sys
import shutil
import os
import glob
import os.path
import re
import argparse
from pathlib import Path
try:
    from gooey import Gooey, GooeyParser #Create GUI from cmd-line app
    gooey_present = True
except:
    gooey_present = False

_CONTENT_PATTERN = re.compile(r"(?<!\\)%[^%]*(?<!\\)%")
_FILENAME_PATTERN = re.compile(r"(?<!\^)%[^%]*(?<!\^)%")

def _find_vars_in_file_names(filelist) -> set:
    vars_ = []
    for file in filelist:
        vars_.extend(re.findall(_FILENAME_PATTERN, file))
    vars_ = [var.strip('%') for var in vars_]
    return set(vars_)

def _find_vars_in_file(filename):
    with open(filename) as f:
        content = f.read()
        vars_ = re.findall(_CONTENT_PATTERN, content)
        vars_ = [var.strip('%') for var in vars_]
        vars_ = set(vars_)
    return vars_

def _find_required_vars(files):
    all_vars = _find_vars_in_file_names(files)
    for file in files:
        if not Path(file).is_dir():
            file_vars = _find_vars_in_file(file)
            all_vars = all_vars.union(file_vars)
    return all_vars

def _list_of_files(path):
    file_iterator = glob.glob(str(path / "**"), recursive=True, include_hidden=True)
    return list(file_iterator)
    
def _unescape_content(string:str):
    return string.replace(r"\%", "%")

def _unescape_filename(string:str):
    return string.replace(r"^%", "%")

    
def _add_free_vars_to_args(free_vars, args):
    """
    Add the command-line input keyword:value pairs to the arguments structure
    """
    for var_ in free_vars:
        namevalue = var_.split(":")        
        setattr(args, namevalue[0], namevalue[1])


def _exception_if_required_args_are_not_present(args, required_vars):
    for varname in required_vars:
        if not hasattr(args, varname) or not getattr(args, varname):
            raise Exception(f'The variable "{varname}" is neccesary for this template, but is not defined in the command line arguments')

def _replace_variables(string, vars, pattern):
    return re.sub(pattern, lambda x:getattr(vars, x.group().strip('%')), string)

def _replace_filenames(files, vars, outdir: Path, files_basedir):        
    for file in files:
        filepath = Path(file)
        relfile = filepath.relative_to(files_basedir)        
        newfile = _replace_variables(str(relfile), vars, _FILENAME_PATTERN)
        newfile = _unescape_filename(newfile)
        newfilepath = outdir / newfile
        Path(os.path.dirname(newfilepath)).mkdir(parents = True, exist_ok = True)
        if not filepath.is_dir():
            shutil.copy(filepath, newfilepath)
        

def _replace_file_contents(file, vars):
    content = Path(file).read_text()
    newcontent = _replace_variables(content, vars, _CONTENT_PATTERN)
    newcontent = _unescape_content(newcontent)
    Path(file).write_text(newcontent)

def _output_path_should_not_exist(output_path:Path, project_name:str):
    if output_path.exists():
        return output_path / project_name
    return output_path

def main(argv):
    args = parse_command_line_arguments(argv)

    
    if not args.template_path.exists():
        print(f"Template folder '{args.template_path}' not found")
        sys.exit(1)
    
    # Find all variables to be replaced in the template
    files = _list_of_files(args.template_path)
    required_vars = _find_required_vars(files)
    if args.variables:
        _add_free_vars_to_args(args.variables, args)
    try:
        _exception_if_required_args_are_not_present(args, required_vars)
    except Exception as e:
        print(e)
        sys.exit(1)

    args.output_path = _output_path_should_not_exist(args.output_path, args.project)

    _replace_filenames(files, args, args.output_path, args.template_path)

    newfiles = _list_of_files(args.output_path)

    for file in newfiles:
        if not Path(file).is_dir():
            _replace_file_contents(file, args)
    print(f"New project created successfully in directory {args.output_path}")


def parse_command_line_arguments(argv):
    program_name = "Create project from template"
    description = "Use this program to generate a new project from a template."
    if gooey_present:
        #GooeyParser extends argparse.ArgumentParser. You can still use this as a command line parser, but it takes the additional "widget" argument for use in the GUI
        ap = GooeyParser(prog=program_name,description=description)
        widgetArg = {'widget':'DirChooser'}
    else:
        ap = argparse.ArgumentParser(prog=program_name,description=description)    
        widgetArg = {}
    ap.add_argument("project",  help="Name of the new project")
    ap.add_argument("template_path",  type=Path, help="Path to folder containing template to create project from", **widgetArg)
    ap.add_argument("output_path", type=Path, help="Path to new project to be created", **widgetArg)
    ap.add_argument("--description", help="Description of the project")
    ap.add_argument("--author", help = "Name of the author of the project")
    ap.add_argument("--email", help = "E-mail of the author of the project")
    ap.add_argument("--variables", type=str, nargs="*", help="Other variables used for replacing values in the template. List in the form 'KEYWORD1:VALUE1 KEYWORD2:VALUE2 keyWord3:Value3'")
    args = ap.parse_args(argv)
    return args


def entry_point():
    main(sys.argv[1:])

if gooey_present:
    @Gooey(required_cols=1, default_size=(500, 780), program_name="Create project from template")
    def entry_point_gui(): #Separate entry point for the GUI
        entry_point()
else:
    def entry_point_gui():
        print("Gooey is required to run the GUI. Type \"pip install gooey\" to install it")
        sys.exit(1)

if __name__ == "__main__":
    entry_point()

