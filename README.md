# Template manager

A small program to generate projects from templates by replacing key names in files and file/folder names by specific values. Templates to use with the template manager can be found in the [templates project](http://devtools/general/templates).

## Creating a new project from an existing template
First, install the program using
```
pip install template-manager
```
To include the gooey-package that is required to run the program as a GUI, install using 
```
pip install template-manager[gui]
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
usage: Create project from template [-h] [--template TEMPLATE] [-o OUTPUT_PATH] [-d DESCRIPTION] [--author AUTHOR] [--email EMAIL] [--variables [VARIABLES ...]] [--git-commit GIT_COMMIT] [--git-folder GIT_FOLDER] [-t SETTINGS_TOML] [--edit-settings] [--list-folders] project

Use this program to generate a new project from a template.

positional arguments:
  project               Name of the new project

options:
  -h, --help            show this help message and exit
  --template TEMPLATE   Location of the template, either a directory or a git repository
  -o OUTPUT_PATH, --output-path OUTPUT_PATH
                        Path to new project to be created. Default is ./<project name>
  -d DESCRIPTION, --description DESCRIPTION
                        Description of the project
  --author AUTHOR       Name of the author of the project
  --email EMAIL         E-mail of the author of the project
  --variables [VARIABLES ...]
                        Other variables used for replacing values in the template. List in the form 'KEYWORD1:VALUE1 KEYWORD2:VALUE2 keyWord3:Value3'
  --git-commit GIT_COMMIT
                        Commit hash if not creating from the head of the default git branch
  --git-folder GIT_FOLDER
                        Folder under the git repo where the template is located. Default is '.'
  -t SETTINGS_TOML, --settings-toml SETTINGS_TOML
                        Path to .template-settings.toml file to use as settings for the project
  --edit-settings       Edit settings such as default template repo and author details
  --list-folders        Output a list of folders in the root of the git repository
```

### GUI
In the command line, type
```
template-gui
```
to start the GUI. 

### Creating your own template
To create your own template, create a new folder containing all files and folders that a new project made from the template should contain. The names of files and folders may contain keywords such as %project%, %author% etc. These will be replaced by the variable values in the newly created project. The contents of the file may also contain such keywords which will be replaced.
You can use any keywords you wish. The keywords "project", "description", "author" and "email" are given by standard command line arguments. Additional special keywords, which you do not need to specify, are "project_snake" (lowercase project with dashes and spaces replaced by underscores), "project_lc" (project lowercase), "project_kebab" (kebab-case: lowercase with spaces replaced by dashes "-"), ProjectPascal (Pascal case: all words capitalized and spaces removed), projectCamel (Camel case: All words except the first capitalized, and spaces removed), PROJECT_UPPER (all uppercase with spaces replaced by underscores)  and "date" (current date). It is recommended to use spaces in the project name, and use these special variables where spaces should be omitted. Any other keywords must be given through the "--variables" option of the command line tool, e.g 

```template-gen --variables "my_var_1:Hello world" my_var_2:somethingelse ...```

### Converting templates to Cookiecutter

Convert a UTF-8 template file using:

```bash
template-to-cookiecutter source.txt -o converted.txt
# Also available without the console script:
python -m template_manager.cookiecutter source.txt -o converted.txt
```

With no input or output path, the command reads stdin or writes stdout. It converts
`%project%` to `{{ cookiecutter.project }}` and conditional blocks to Jinja:
`%if(enabled)%` becomes `{% if ... %}`, `%elseif(other)%` becomes `{% elif ... %}`,
and `%else%` / `%endif%` become `{% else %}` / `{% endif %}`. Nested blocks are
supported; unbalanced blocks raise an error. Conditions check that the variable
exists and is neither boolean false nor a case-insensitive string `"false"`.

The Python function also accepts filename strings:

```python
from template_manager.cookiecutter import convert_template

convert_template("Hello %name%")  # "Hello {{ cookiecutter.name }}"
convert_template("%name%.py", filename=True)  # "{{ cookiecutter.name }}.py"
convert_template("%name%", namespace="")  # "{{ name }}"
```

Use `--namespace ''` for bare Jinja variables or `--filename` for filename strings.
Escaped percent signs (`\%` in contents, `^%` in filenames) become literal percent
signs. File conversion preserves line endings. This converts strings or individual
files; rename template paths separately and provide the variables in your
Cookiecutter project's `cookiecutter.json`. Derived template-manager variables
such as `project_snake` must also be defined there.

#### Important note on creating your own template:
Since the character "%" is used for variable names, any occurences of this character that should not be replaced need to be escaped. In the file contents, it should be escaped as "\\%". Since "\\" is illegal in file names, the percent sign should be escaped as "^%" in file names (only relevant if any of your files should actually contain the percent-sign after creation). A limitation of this scheme is that you cannot have a variable immediately following a '\\' character in code or a '^' character in file names.
