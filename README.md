# Template generator

A small program to generate templates by replacing key names in files and file/folder names by specific values. Templates to use with the template generator can be found in the [templates project](http://devtools/general/templates).

## Creating a new project from an existing template
First, install the program using
```
pip install template-generator
```
You can now either run the program as a command line application, or as a GUI.

### Command line application
Usage:
```
template-gen templates/python_project_simple_release my_new_project my_new_project_folder --description "A new project to demonstrate the template builder" --author "Ola Olsen" --email "ola@olsen.com"
```
In this example, the template code inside "templates/python_project_simple_release" will be copied, and a new project will be created in "my_new_project_folder". In this project, file names and file contents with keywords in the form %keyword% will be replaces by the values given on the command line (i.e. project name, author, description etc.).

Output of `template-gen -h`:
```
usage: template-gen [-h] [--description DESCRIPTION] [--author AUTHOR] [--email EMAIL] [--variables [VARIABLES ...]] template_folder project output_path

Use this program to generate a new project from one of the templates found in the same folder, replacing keys with values within the files.

positional arguments:
  template_folder               Folder containing template to create project from
  project                       Name of the new project
  output_path                   New path to created project

options:
  -h, --help                    show this help message and exit
  --description DESCRIPTION     Description of the project
  --author AUTHOR               Name of the author of the project
  --email EMAIL                 E-mail of the author of the project
  --variables [VARIABLES ...]   Other variables used for replacing values in the template. 
                                List in the form 'KEYWORD1:VALUE1 KEYWORD2:VALUE2 keyWord3:Value3'
```

### GUI
In the command line, type
```
template-gui
```
to start the GUI. 

### Creating your own template
To create your own template, create a new folder containing all files and folders that a new project made from the template should contain. The names of files and folders may contain keywords such as %project%, %author% etc. These will be replaced by the variable values in the newly created project. The contents of the file may also contain such keywords which will be replaced.
You can use any keywords you wish. The keywords "project", "description", "author" and "email" are given by standard command line arguments. Any other keywords must be given through the "--variables" option of the command line tool, e.g 

```template-gen --variables "my_var_1:Hello world" my_var_2:somethingelse ...```

#### Important note on creating your own template:
Since the character "%" is used for variable names, any occurences of this character that should not be replaced need to be escaped. In the file contents, it should be escaped as "\\%". Since "\\" is illegal in file names, the percent sign should be escaped as "^%" in file names (only relevant if any of your files should actually contain the percent-sign after creation). A limitation of this scheme is that you cannot have a variable immediately following a '\\' character in code or a '^' character in file names.