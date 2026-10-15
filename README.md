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
usage: Create project from template [-h] [--template TEMPLATE] [-o OUTPUT_PATH] [-d DESCRIPTION] [--author AUTHOR] [--email EMAIL] [--uuid-seed UUID_SEED] [--variables [VARIABLES ...]] [--git-commit GIT_COMMIT] [--git-folder GIT_FOLDER] [-t SETTINGS_TOML] [--edit-settings] [--list-folders] project

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
  --uuid-seed UUID_SEED  Seed for named UUIDs; generated randomly if omitted
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

### Choosing template syntax

`template-gen` supports both legacy `%project%` placeholders and Cookiecutter/Jinja
placeholders, including `{{ project }}` and `{{ cookiecutter.project }}`. Jinja
templates support `{% if condition %}`, `{% elif condition %}`, `{% else %}`, and
`{% endif %}`, including nested blocks, filters, and expressions. Variables and
conditionals work in file contents and file/directory names. Supply values using
the existing project arguments and `--variables KEY:VALUE`.
If a Jinja path component renders empty, that file or directory and its descendants
are excluded. Rendered paths must stay inside the output directory; absolute paths,
parent traversal outside it, and escapes through existing symlinks are rejected.

```bash
template-gen "My Project" --template ./template --cookiecutter-syntax --no-gitlab-project
template-gen "My Project" --template ./template --legacy-syntax --no-gitlab-project
```

The two flags are mutually exclusive. Without either flag, Jinja `{{ ... }}` or
`{% ... %}` markers in template text or relative paths select Cookiecutter mode;
otherwise legacy mode is used. Binary contents are ignored during detection and
copied unchanged. For templates containing both syntaxes, Cookiecutter takes
precedence; use an explicit flag to keep the other syntax as literal text.
The syntax preference is stored in `.template_settings.toml`: `auto` when neither
flag was supplied, or the explicitly selected mode. Automatic mode detects syntax
again during recreation and updates, so a template can migrate between legacy and
Cookiecutter syntax. An explicit syntax flag overrides the stored preference.
Settings previously saved with a detected `legacy` or `cookiecutter` value cannot
be distinguished from explicit choices; change that value to `auto` to enable
autodetection for those projects.

Cookiecutter mode uses Jinja truthiness: a missing conditional flag is false,
while a missing variable that is actually rendered raises an error. CLI values
are strings, so test false-valued options explicitly, for example
`{% if cookiecutter.enabled == 'true' %}`. Unlike legacy conditions, the nonempty
string `"false"` is truthy in a plain Jinja `{% if enabled %}`. This mode renders
template syntax using the existing arguments; it does not load `cookiecutter.json`
or run Cookiecutter hooks.

### Creating your own template
To create your own template, create a new folder containing all files and folders that a new project made from the template should contain. The names of files and folders may contain keywords such as %project%, %author% etc. These will be replaced by the variable values in the newly created project. The contents of the file may also contain such keywords which will be replaced.
You can use any keywords you wish. The keywords "project", "description", "author" and "email" are given by standard command line arguments. Additional special keywords, which you do not need to specify, are "project_snake" (lowercase project with dashes and spaces replaced by underscores), "project_lc" (project lowercase), "project_kebab" (kebab-case: lowercase with spaces replaced by dashes "-"), ProjectPascal (Pascal case: all words capitalized and spaces removed), projectCamel (Camel case: All words except the first capitalized, and spaces removed), PROJECT_UPPER (all uppercase with spaces replaced by underscores)  and "date" (current date). It is recommended to use spaces in the project name, and use these special variables where spaces should be omitted. Any other keywords must be given through the "--variables" option of the command line tool, e.g 

```template-gen --variables "my_var_1:Hello world" my_var_2:somethingelse ...```

#### Named UUIDs

Use `%uuid(name)%` in legacy templates, or `{{ uuid('name') }}`
in Jinja templates rendered by template-manager, in file contents or file/folder names:

```text
id = "%uuid(main)%"
reference = "%uuid(main)%"
other_id = "%uuid(other)%"
```

The equivalent Jinja template is:

```jinja
id = "{{ uuid('main') }}"
reference = "{{ uuid('main') }}"
other_id = "{{ uuid('other') }}"
```

Jinja requires quotes around literal names.
UUID calls follow the selected syntax's escaping and conditional rules, and
Jinja filters work normally. Bare `uuid(name)` and `uuid[name]` remain literal.
Escape legacy placeholders as `\%uuid(name)\%` in contents or
`^%uuid(name)^%` in paths. Use Jinja raw blocks for literal Cookiecutter examples.
`template-to-cookiecutter` converts `%uuid(name)%` to the corresponding Jinja call.

Template-manager provides the `uuid` helper automatically. Standalone Cookiecutter
does not provide this named UUID helper: rendering these calls there requires a
[custom Jinja extension](https://cookiecutter.readthedocs.io/en/stable/advanced/template_extensions.html)
that registers a global function named `uuid`. Such an extension can implement
the seed-and-name algorithm below without modifying Cookiecutter itself. It would
need to reuse a persisted project seed to preserve IDs across regeneration.
No such extension is bundled here; Cookiecutter's built-in `uuid4()` generates
random IDs and is not a replacement for this helper.

Every occurrence of the same name receives the same UUID throughout the project.
Names are case-sensitive and must be nonempty strings without parentheses,
percent signs or newlines. No command line variable is needed for UUID names.
UUIDs use UUIDv5: the namespace is `uuid5(NAMESPACE_URL, seed)`, and each value
is `uuid5(namespace, name)`. Adding or reordering names does not change existing IDs.

A random seed is generated for each new project and saved as `uuid_seed` in
`.template_settings.toml`. Recreation with `--settings-toml` and updates with
`template-update` reuse this seed, preserving UUIDs. Older projects without a seed
receive one during their next update.

You can supply any nonempty seed string explicitly with `--uuid-seed`:

```sh
template-gen "My project" --template ./my-template --uuid-seed "my-project-seed"
```

Using the same seed and name produces the same UUID, even in separate projects.
Keep the saved seed and placeholder names unchanged to preserve IDs across updates.

### Converting templates to Cookiecutter

Convert a UTF-8 template file or folder using:

```bash
template-to-cookiecutter source.txt -o converted.txt
template-to-cookiecutter ./template-folder -o ./converted-folder
# Also available without the console script:
python -m template_manager.cookiecutter source.txt -o converted.txt
```

For a folder input, all files are converted recursively, including template
placeholders in relative filenames and folder names. `-o` is required and must
be a filename for file input or a folder for folder input. The command converts
`%project%` to `{{ cookiecutter.project }}` and conditional blocks to Jinja:
`%if(enabled)%` becomes `{% if ... %}`, `%elseif(other)%` becomes `{% elif ... %}`,
and `%else%` / `%endif%` become `{% else %}` / `{% endif %}`. Nested blocks are
supported; unbalanced blocks raise an error. Conditions check that the variable
exists and is neither boolean false nor a case-insensitive string `"false"`.
Named UUIDs become `{{ uuid('name') }}` calls regardless of `--namespace`.
This converter changes syntax for rendering with template-manager; it does not
generate a complete standalone Cookiecutter project or install extensions.
Standalone Cookiecutter use of named UUIDs requires the extension described above.

The Python function also accepts filename strings:

```python
from template_manager.cookiecutter import convert_template

convert_template("Hello %name%")  # "Hello {{ cookiecutter.name }}"
convert_template("%name%.py", filename=True)  # "{{ cookiecutter.name }}.py"
convert_template("%name%", namespace="")  # "{{ name }}"
```

Use `--namespace ''` for bare Jinja variables or `--filename` for filename strings.
Escaped percent signs (`\%` in contents, `^%` in filenames) become literal percent
signs. File conversion preserves line endings. For standalone Cookiecutter use,
provide the variables in your project's `cookiecutter.json`. Derived template-manager variables
such as `project_snake` must also be defined there.

#### Important note on creating your own template:
Since the character "%" is used for variable names, any occurences of this character that should not be replaced need to be escaped. In the file contents, it should be escaped as "\\%". Since "\\" is illegal in file names, the percent sign should be escaped as "^%" in file names (only relevant if any of your files should actually contain the percent-sign after creation). A limitation of this scheme is that you cannot have a variable immediately following a '\\' character in code or a '^' character in file names.
