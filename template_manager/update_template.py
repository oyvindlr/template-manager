"""
Functions used to update a project based on a given template to the latest version of the
template, using git's three-way merge
"""
from template_manager import project_from_template
import argparse
from pathlib import Path
import sys
import tempfile
import template_manager.git_wrapper  as git
import toml
import os
import shutil



def _toml_file_with_updated_commit_hash(tomlfile, hash, uuid_seed=None):
    d = toml.load(tomlfile)
    d["git_commit"] = str(hash)
    if uuid_seed is not None:
        d["uuid_seed"] = uuid_seed
    new_toml =  tempfile.NamedTemporaryFile(mode="w", delete=False, encoding = 'utf8')
    toml.dump(d, new_toml)
    new_toml.close()
    return new_toml



def _overwrite_exclude_git_dir(source: Path, dest: Path, source_gitdir = ".git"):
    if dest.exists():
        _remove_all_but_git_dir(dest)
    else:
        dest.mkdir()
    _copy_all_but_one_dir(source, dest, source_gitdir)


def _copy_all_but_one_dir(source: Path, dest: Path, retain_dir: str):
    """
    Recursively copy contents of `source` into `dest`, skipping any directory
    whose name equals `retain_dir` (e.g., '.git'), at any depth.
    """
    dest.mkdir(parents=True, exist_ok=True)

    for entry in source.iterdir():
        # Skip the excluded directory (by name) at any depth
        if entry.is_dir() and entry.name == retain_dir:
            continue

        target = dest / entry.name

        if entry.is_dir():
            # Recreate directory and recurse
            target.mkdir(exist_ok=True)
            _copy_all_but_one_dir(entry, target, retain_dir)
        else:
            # For files (and symlinks), copy with metadata
            # Note: on Windows, symlink creation often requires privileges;
            # copy2 with follow_symlinks=True (default) mirrors the original behavior.
            shutil.copy2(entry, target)


def _remove_all_but_git_dir(root: Path):
    for entry in root.iterdir():
        if entry.name == ".git":
            continue
        if entry.is_file() or entry.is_symlink():
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)

   


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
    # Older projects have no seed yet. Reuse the seed from the first generation
    # for the updated template too, and persist it in the merged settings.
    uuid_seed = toml.load(proj_dir / ".template_settings.toml")["uuid_seed"]
    
    #Overwrite new settings_toml with original, since changes in project_from_template may change it's content and cause conflicts
    os.remove(proj_dir / ".template_settings.toml")
    shutil.copyfile(settings_toml, proj_dir / ".template_settings.toml")

    manifest_name = ".template_render_manifest.json"
    # Provenance is regenerated metadata, never a three-way-merged source file.
    (proj_dir / manifest_name).unlink(missing_ok=True)

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
    new_toml_file = _toml_file_with_updated_commit_hash(settings_toml, args.commit, uuid_seed)
    project_creation_args[1] = new_toml_file.name
    other_temp_dir = tempfile.TemporaryDirectory()    
    project_creation_args[3] = other_temp_dir.name
    if args.variables:
        project_creation_args.append("--variables")        
        project_creation_args.extend(args.variables)
    other_proj_dir = project_from_template.main(project_creation_args)
    new_manifest = (other_proj_dir / manifest_name).read_bytes()
    (other_proj_dir / manifest_name).unlink()
    _overwrite_exclude_git_dir(other_proj_dir, proj_dir)

    print("Commiting files to template branch...")
    git.add_all(proj_dir)
    git.commit(proj_dir, "Update template")

    print("Checking out project branch...")
    git.checkout(proj_dir, "project")

    print("Copying project to temporary repository...")
    _overwrite_exclude_git_dir(args.directory, proj_dir)
    (proj_dir / manifest_name).unlink(missing_ok=True)

    print("Committing existing project into temporary repository...")
    git.add_all(proj_dir)
    git.commit(proj_dir, "Update project")

    print("Merging new template into project...")
    conflicts = git.merge(proj_dir, "template")
    
    print("Copying merged repo contents into local project directory...")
    _overwrite_exclude_git_dir(proj_dir, args.output_path)
    (args.output_path / manifest_name).write_bytes(new_manifest)

    print(f"Merging completed! There were {len(conflicts)} merge conflicts.")
    if len(conflicts) > 0:
        print("The following conflicts need to be resolved manually: ")
        for c in conflicts:
            print(c)



def _parse_arguments(argv):
    parser = argparse.ArgumentParser("template-update", description="Update project to latest version of project: Uses git's three way merge to merge the latest template changes into a project based on an earlier version of the template")
    parser.add_argument("-d", "--directory", help="Directory containing project. Defaults to the current directory.", type=Path, default=Path("."))
    parser.add_argument("-o", "--output-path", type=Path, help="Path where the updated project will be stored. By default, the project will be updated in-place.", default=None)
    parser.add_argument("--commit", help="Instead of updating to the latest template version, update to a specific version given by the given git commit hash/branch/tag.")
    parser.add_argument("--variables", type=str, nargs="*", help="Other variables used for replacing values in the template. List in the form 'KEYWORD1:VALUE1 KEYWORD2:VALUE2 keyWord3:Value3'")
    args = parser.parse_args(argv)
    if args.output_path is None:
        args.output_path = args.directory
    return args


def entry_point():
    main(sys.argv[1:])

if __name__ == "__main__":
    entry_point()
