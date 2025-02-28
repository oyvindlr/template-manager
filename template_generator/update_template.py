"""
Functions used to update a project based on a given template to the latest version of the
template, using git's three-way merge
"""
from template_generator import project_from_template
import argparse
from pathlib import Path
import sys
import tempfile
import template_generator.git_wrapper  as git
import toml
import os
import shutil



def _toml_file_with_updated_commit_hash(tomlfile, hash):
    d = toml.load(tomlfile)
    d["git_commit"] = str(hash)
    new_toml =  tempfile.NamedTemporaryFile(mode="w", delete=False, encoding = 'utf8')
    toml.dump(d, new_toml)
    new_toml.close()
    return new_toml



def _overwrite_exclude_git_dir(source, dest, source_gitdir = ".git"):
    _remove_all_but_git_dir(dest)
    _copy_all_but_one_dir(source, dest, source_gitdir)

def _copy_all_but_one_dir(source, dest, retain_dir):
    for root, dirs, files in os.walk(source, topdown=True):
        relroot = Path(root).relative_to(source)
        for file in files:
            shutil.copy2(Path(root) / file, dest / relroot / file)            
        if retain_dir in dirs:
            dirs.remove(retain_dir)
        for dir in dirs:
            os.mkdir(dest / relroot / dir)

def _remove_all_but_git_dir(dir):
    for root, dirs, files in os.walk(dir, topdown=False):
        if root.find(".git") < 0:
            for file in files:
                os.remove(Path(root) / file)
            if ".git" in dirs:
                dirs.remove(".git")
            for dir in dirs:
                os.rmdir(Path(root)/dir)
   


def main(argv):
    
    args = _parse_arguments(argv)

    settings_toml = args.directory / ".template_settings.toml"
    if not settings_toml.exists():
        print('Error: The project to update must contain a ".template_settings.toml" file')
        sys.exit(1)

    temp_dir = tempfile.TemporaryDirectory()


    print("Recreating original empty project from template...")
    project_creation_args = ["--settings-toml", str(settings_toml), "--output-path", temp_dir.name, "--no-gitlab-project"]
    proj_dir = project_from_template.main(project_creation_args)
    
    #Overwrite new settings_toml with original, since changes in project_from_template may change it's content and cause conflicts
    os.remove(proj_dir / ".template_settings.toml")
    shutil.copyfile(settings_toml, proj_dir / ".template_settings.toml")

    print("Initializing temporary repository to utilize git merge...")
    git.init(proj_dir)

    print("Committing original project from template...")
    git.add_all(proj_dir)
    git.commit(proj_dir, "Initial commit")

    print("Creating two new branches which will eventually be merged...")
    git.branch(proj_dir, "template")
    git.branch(proj_dir, "project")
    
    print("Checking out template branch...")
    git.checkout(proj_dir, "template")

    print("Updating to latest template...")
    new_toml_file = _toml_file_with_updated_commit_hash(settings_toml, args.hash)
    project_creation_args[1] = new_toml_file.name
    other_temp_dir = tempfile.TemporaryDirectory()    
    project_creation_args[3] = other_temp_dir.name
    other_proj_dir = project_from_template.main(project_creation_args)
    _overwrite_exclude_git_dir(other_proj_dir, proj_dir)

    print("Commiting files to template branch...")
    git.add_all(proj_dir)
    git.commit(proj_dir, "Update template")

    print("Checking out project branch...")
    git.checkout(proj_dir, "project")

    print("Copying project to temporary repository...")
    _overwrite_exclude_git_dir(args.directory, proj_dir)

    print("Committing existing project into temporary repository...")
    git.add_all(proj_dir)
    git.commit(proj_dir, "Update project")

    print("Merging new template into project...")
    conflicts = git.merge(proj_dir, "template")
    
    print("Copying merged repo contents into local project directory...")
    _overwrite_exclude_git_dir(proj_dir, args.directory)

    print(f"Merging completed! There were {len(conflicts)} merge conflicts.")
    if len(conflicts) > 0:
        print("The following conflicts need to be resolved manually: ")
        for c in conflicts:
            print(c)



def _parse_arguments(argv):
    parser = argparse.ArgumentParser("template-update", description="Update project to latest version of project: Uses git's three way merge to merge the latest template changes into a project based on an earlier version of the template")
    parser.add_argument("-d", "--directory", help="Directory containing project. Defaults to the current directory.", type=Path, default=Path("."))
    parser.add_argument("--hash", help="Instead of updating to the latest template version, update to a specific version given by the git commit hash.")
    args = parser.parse_args(argv)
    return args


def entry_point():
    main(sys.argv[1:])

if __name__ == "__main__":
    entry_point()