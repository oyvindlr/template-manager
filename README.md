# Template manager

A small program to generate projects from templates by replacing key names in files and file/folder names by specific values. Templates to use with the template manager can be found in the [templates project](http://devtools/general/templates).

## Installing the reverse-sync review skill

The package includes an agent skill for promoting reusable project changes back
into the template the project was created from. After installing template-manager,
install the skill for your local coding agents:

```sh
template-install-skill
```

The command detects Claude Code, Codex, and GitHub Copilot through their executables
on `PATH`, existing configuration directories, or installed extensions in common
VS Code, VS Code Insiders, and VS Code Server extension directories. It copies
`reverse-sync-review/SKILL.md` into each detected agent's personal skills directory
and prints each installed path:

| Agent | Default skills directory |
| --- | --- |
| [Claude Code](https://code.claude.com/docs/en/skills) | `~/.claude/skills` |
| [Codex](https://developers.openai.com/codex/skills/) | `~/.agents/skills` |
| [GitHub Copilot](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills) | `~/.copilot/skills` |

`CLAUDE_CONFIG_DIR` and `COPILOT_HOME` override their respective configuration and
skills roots. `CODEX_HOME` is checked for Codex detection; Codex's personal skills
still go into `~/.agents/skills`. Detection does not launch clients or read
credentials. No detected client means no files are written and the command exits
with guidance to specify a destination. Other editors or custom layouts may need
an explicit destination, which bypasses detection:

```sh
template-install-skill --destination ~/.agents/skills
template-install-skill --destination .agents/skills
```

`--destination` names the parent skills directory; the command creates the
`reverse-sync-review` subdirectory. Choose the discovery directory supported by
your agent. Re-running the command leaves identical copies alone; use `--force`
to replace an edited or older copy after upgrading template-manager. Copies are
updated only when you run the command. Nothing is copied into template-manager's
global configuration directory. The skill is bundled as package data (the change
in `setup.py`); installing the Python package alone does not install it into any
agent. The skill is also available directly in
the installed package at `template_manager/skills/reverse-sync-review/SKILL.md`.

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

### Updating a project

Run `template-update -d ./my-project` to merge the latest template into a project.
Commit or stash changes first: the command exits with a warning if the project
repository has staged, unstaged, or untracked files. An existing repository at
`--output-path` must also be clean.

Updates leave unchanged files in place and overwrite changed regular files
without deleting them first. Files are deleted only when removed by the merge
or replaced by a different kind of entry (for example, a symlink). For Git
projects, ignored files such as Visual Studio's `.vs` directory and build
outputs are left untouched during snapshots, backups, updates, and rollback.
This allows updates while an IDE is open when its file handles permit writing;
files locked against writing or required deletion can still block an update.

If files cannot be overwritten, close programs using them and choose **retry**
or **cancel**. Cancellation restores tracked project files from Git and recovers
other original files from a temporary backup. Folders without Git are restored
from the backup. End-of-input or Ctrl+C at the prompt also cancels. If restoration
fails, the error reports the retained recovery directory for manual recovery.

### Reverse sync: reviewing project improvements for the template

`template-reverse-sync` extracts a small review bundle from committed project
changes. It stores the last reviewed project commit in the custom Git ref
`refs/template-manager/reverse-sync/reviewed`, without adding a file or commit to
the project. Extraction never advances this checkpoint.

For an agent-assisted review, prefer `review`. It adds repository, template,
checkpoint, commit, classification, and per-file diff statistics to the bundle:

```sh
template-reverse-sync review --until HEAD -o reverse-sync-review
```

If the checkpoint is absent, `review` defaults to the first merge commit after
the earliest project commit containing `.template_settings.toml`. This supports
projects that merged a separately generated template history into their existing
history. Override the heuristic with `--since` when it is not the intended
baseline. `extract` retains its stricter behavior and requires either a checkpoint
or explicit `--since`.

The review bundle contains:

- `review.json`: machine-readable review context and full changed-path inventory.
- `review.md`: compact review table and suggested next steps.
- `changes.diff`: changes selected by the candidate heuristics.
- `all-changes.diff`: the complete committed net diff for selective inspection.

Each inventory entry includes a lightweight classification hint and diff
statistics. Hints are triage aids, not final dispositions. The report also resolves
the local and selected remote checkpoint without treating access errors as absence,
and resolves the intended template PR base (`main` by default):

```sh
template-reverse-sync review --remote origin --template-base main
template-reverse-sync review --since <explicit-start> --until <target-commit>
template-reverse-sync --version
```

For first use without a checkpoint, extract from an explicit starting commit
without creating a ref:

```sh
template-reverse-sync extract --since <starting-project-commit> --until HEAD -o reverse-sync-output
# Also available without installing the console entry point:
python -m template_manager.reverse_sync extract --since <starting-project-commit>
```

Custom refs are not fetched by ordinary clones. When using the legacy extraction
interface, fetch the remote checkpoint into a separate observed ref, compare it
with any local checkpoint, and choose the intended baseline explicitly. Do not
force-fetch over a local checkpoint. For guarded workspace preparation and
checkpoint publication, see the automated workflow below.

The output contains `changes.diff` and `manifest.json`. The manifest records full
start/end commit hashes, included and excluded paths, and selection reasons. The
diff contains the net changes between those commits, so reverted changes disappear.
Uncommitted and untracked files are ignored. Both renames and deletions are included;
binary changes include Git's binary patch data. Empty output is successful and leaves the checkpoint unchanged.

Candidates are files present in the rendered template at either endpoint, common
infrastructure filenames/directories, and `.toml`, `.ini`, `.yaml`, `.yml`, `.json`,
`.xml`, or `.cfg` files. Other changes are listed as `no-rule-matched`; this is a
heuristic, not proof of irrelevance. Optional repeated `--include` and `--exclude`
arguments match repository-relative paths using case-sensitive shell-style globs
(where `*` can match `/`). Exclusions take priority, including for template paths.
For a rename, either path can cause inclusion or exclusion.

```sh
template-reverse-sync extract --include 'scripts/*' --exclude 'fixtures/*'
template-reverse-sync extract --since <explicit-start> --until <target-commit>
```

Global options `-d/--directory` and `--checkpoint-ref` go before the subcommand.
Run from the project repository root. `.template_settings.toml` is read from both
committed endpoints, and its referenced template revision must be available. The
existing renderer reconstructs the template paths in temporary directories, using
the installed template-manager version and saved date/UUID seed. Relative local
template locations are resolved against the project root. Templates with unsaved
local changes are rejected. Historical projects missing a date or UUID seed use
fixed fallback values; review the manifest warning about paths containing those
values. If template settings changed, both rendered path sets are considered, but
imported template updates are not subtracted from the diff in this initial version.

After reviewing the entire bundle and obtaining explicit approval, advance to
the **exact `until` SHA**, even if HEAD has since moved. Prepared workspaces use
the guarded command, which verifies recorded dispositions and remote observations:

```sh
template-reverse-sync mark-reviewed --from-review /path/to/review/review.json \
  --push origin --expected-remote <observed-remote-checkpoint-sha>
```

The expected remote SHA is its observed value, which need not equal the review's
`since`. Use an empty value only for confirmed absence. Omit push options for a
local-only update. The legacy `mark-reviewed <reviewed-until-sha>` is local-only.

Only advance when every change in the range has been dealt with, including rejected
candidates; leave the checkpoint alone if work is deferred. Backward or divergent
local checkpoint moves are rejected. A missing ref or unavailable history fails with
an actionable error instead of silently choosing a starting point.

For GitLab CI, a minimal opt-in job in a generated project looks like this. It needs
template-manager installed, read access to the pinned template repository, and enough
project history. Adapt installation to your package registry or CI image:

```yaml
reverse-sync:
  stage: test
  variables:
    GIT_DEPTH: "0"
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
      when: manual
      allow_failure: true
  script:
    - pip install template-manager
    - git fetch origin refs/template-manager/reverse-sync/reviewed:refs/template-manager/reverse-sync/observed
    - template-reverse-sync extract --since refs/template-manager/reverse-sync/observed --until "$CI_COMMIT_SHA" -o reverse-sync-output
  artifacts:
    paths:
      - reverse-sync-output/
    expire_in: 30 days
```

Review and checkpoint advancement happen separately from this read-only job. An
expired artifact can be regenerated using the same endpoint SHAs. No remote refs
are pushed automatically, and no CI write credential is needed for extraction.

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

## Automated reverse-sync workspace

The existing `review` and `extract` interfaces remain available. For a resumable
pipeline, use a fresh workspace outside both source repositories:

```sh
template-reverse-sync --directory /path/to/project prepare \
  --since <starting-commit> --until HEAD --remote origin --template-base main \
  --workspace /path/to/review
# Omit --since when using an existing checkpoint or the automatic first-merge baseline.
# Read review.md; set decisions.json dispositions before applying accepted edits.
template-reverse-sync apply --workspace /path/to/review
template-reverse-sync validate --workspace /path/to/review --run-tests
template-reverse-sync publish --workspace /path/to/review --title "Improve generated builds"
```

`prepare` resolves full SHAs once, caches Git objects by source and renders by
source tree, tool version, and settings, and creates independent `template`,
`base`, and `original` checkouts. `workspace.json` records the endpoints, paths,
branch, commands, checkpoint observations, and publication result. Use `--cache`
to select a cache directory (default: the platform's template-manager user cache).
Local and remote checkpoint differences stop preparation for reconciliation;
a missing checkpoint uses the existing first-merge strategy, or explicit `--since`.
Uncommitted project edits remain outside the committed review range.

`decisions.json` contains one entry per changed path group, including exclusions.
Keep the inventory intact and record `accepted`, `excluded`, `already upstream`,
or `deferred` and a reason. All non-upstream entries initially require review.
`apply` processes only accepted modifications and preserves existing placeholders.
It deliberately leaves ambiguous spans, changed upstream files, substitutions,
conditionals, additions/deletions/renames, binary data, and modes for manual edits.
Inspect `application` and `reason` after running it. Repeated runs preserve edits.
Exact rendered matches at the current base receive an `already upstream` hint.

The default alternate fixture changes the project name and its derived forms.
Pass `--alternate-settings alternate.toml` to prepare, or edit the workspace's
`alternate-settings.toml`, to change affected custom parameters and exercise flags.
The overlay cannot change the source location/revision, subdirectory, date, or UUID
seed during preparation. Additional condition states can be checked with separate
fixture runs. Review generated settings locally; they may contain private values.

Validation always renders the actual edited snapshot, including uncommitted
changes. Every run uses fresh generated output; immutable render caching avoids
repeating generation. It checks text and filenames for simple unresolved
placeholders and source values in alternate output. Checks are conservative
heuristics; escaped placeholders or intentional literal examples can be findings.
`validation.json` and `validation.md` distinguish generation/static checks from
executed template tests. The base is tested only when the patched fixture fails;
identical findings and test failures are `pre-existing-failure`, recognizable
network failures are `environment/network-failure`, differing failures are
`regression`, and inconclusive baseline errors are `unresolved-failure`.
Failures return a nonzero CLI exit status. Logs remain in the workspace.

Publication requires resolved dispositions and validation of the current source
snapshot. Failing validation requires `--draft`. The command retains a binary-capable
`template.patch`, verifies it against the clean base, commits/pushes without force,
and creates or updates a PR/MR through authenticated `gh`/`glab` CLIs. Choose
`--provider github|gitlab` when autodetection from the template URL is unsuitable.
It never merges or advances the project checkpoint. On failure, the patch, local
branch, and any pushed branch remain available for recovery.

After explicit approval, advance and optionally publish the **review's exact
until SHA**, not the latest HEAD:

```sh
template-reverse-sync --directory /path/to/project mark-reviewed \
  --from-review /path/to/review/review.json --push origin --expected-remote <observed-sha>
```

Omit both push options for a local update. Use `--expected-remote ''` only for
recorded absence. All entries need final dispositions; accepted changes require
a recorded PR/MR and the expected published branch commit. Changed local/remote
observations stop the operation. A remote push uses an explicit lease; push failure
reports local success separately. The legacy `mark-reviewed <commit>` remains
available for deliberate local-only operations.

`template-reverse-sync preflight --remote origin --timeout 20` times a read-only
Git connectivity check and distinguishes common TLS, DNS, authentication, and
timeout failures. It does not change certificates or disable TLS verification.
Informational X.509 messages alone are not certificate failures.

### Render provenance and CLI settings

Generation now writes `.template_render_manifest.json`: schema/renderer version,
pinned template revision, effective settings hash, and per-file template/rendered
paths and SHA-256 hashes. It stores no raw parameter values. Reverse extraction
uses compatible historical mappings and falls back to rendering for older projects.
`template-update` refreshes this generated metadata without three-way merging it.
The manifest describes template output, not subsequent application edits.

A project name is now accepted with saved settings:

```sh
template-gen "Alternate Name" --settings-toml source.toml -o ./alternate --no-gitlab-project
```

The explicit positional name overrides the saved name; derived names are recomputed.
Other saved-settings precedence is unchanged.

### Template test contract and CI

Place `.template-tests.toml` in the template subdirectory:

```toml
command = ["python", "{template}/tests/check_generated.py", "{output}"]
timeout = 300
```

The command is an argv array, executed without a shell from the generated output
root. The contract is rendered with each fixture, so existing template parameters
can be used in its arguments. `{template}` points to the actual template snapshot; `{output}` points to a
fresh generated project. Tests run for both source and alternate fixtures. Review
the contract/scripts, then pass `--run-tests` to authorize their execution. No
contract means generation/static checks only. Avoid secrets in test output; logs
remain local. Exclude test tooling from published artifacts as appropriate for the
template. The same scripts work in template CI without a project Git history:

```sh
template-reverse-sync test-template --template ./my-template \
  --settings ./tests/source.toml --alternate-settings ./tests/alternate.toml \
  --workspace ../template-test-output --run-tests
```

A template CI job should install its actual build dependencies, run this command
on each PR/MR and the main branch, and retain `validation.json`, `validation.md`,
and logs on failure. Use a fresh workspace each job. Test the installer from clean
output, including RID-specific restore/publish, stale publish-file cleanup, MSI
existence, and framework-dependent output excluding `hostfxr.dll`. Ready-to-adapt
PowerShell and CI examples are in `examples/template-tests/`; they require the
actual template's project names/build paths and a Windows toolchain. They are
examples, not claims that a Windows installer was built in template-manager CI.
