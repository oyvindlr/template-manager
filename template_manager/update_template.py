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
import stat
from contextlib import ExitStack



def _toml_file_with_updated_commit_hash(tomlfile, hash, uuid_seed=None):
    d = toml.load(tomlfile)
    d["git_commit"] = str(hash)
    if uuid_seed is not None:
        d["uuid_seed"] = uuid_seed
    new_toml =  tempfile.NamedTemporaryFile(mode="w", delete=False, encoding = 'utf8')
    toml.dump(d, new_toml)
    new_toml.close()
    return new_toml



def _overwrite_exclude_git_dir(source: Path, dest: Path, source_gitdir = ".git", *, remove_files=None):
    """Synchronize project files without replacing existing regular files."""
    result_files = set(_file_paths(source, source_gitdir))
    if dest.exists():
        managed_files = set(_file_paths(dest)) if remove_files is None else remove_files
        obsolete = managed_files - result_files
        for name in result_files:
            entry, target = source / name, dest / name
            # Symlinks must be replaced rather than followed when writing.
            if target.is_symlink():
                if not entry.is_symlink() or os.readlink(entry) != os.readlink(target):
                    obsolete.add(name)
            elif target.exists() and (entry.is_symlink() or target.is_dir()):
                obsolete.add(name)
        _remove_selected_files(dest, obsolete)
    else:
        dest.mkdir(parents=True)
    for name in result_files:
        entry, target = source / name, dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if entry.is_symlink():
            if not target.is_symlink():
                target.symlink_to(os.readlink(entry), target_is_directory=entry.is_dir())
        elif target.is_file() and _same_contents(entry, target):
            # Ignore timestamp differences, but retain executable/permission changes.
            if stat.S_IMODE(entry.stat().st_mode) != stat.S_IMODE(target.stat().st_mode):
                shutil.copystat(entry, target)
        else:
            # copy2 opens existing files for writing; it does not unlink them.
            shutil.copy2(entry, target)


def _same_contents(source, destination):
    """Compare bytes without a stat-based cache (also safe after partial writes)."""
    if source.stat().st_size != destination.stat().st_size:
        return False
    with source.open("rb") as original, destination.open("rb") as existing:
        while True:
            chunk = original.read(1024 * 1024)
            if chunk != existing.read(1024 * 1024):
                return False
            if not chunk:
                return True


def _copy_selected_files(source, dest, files):
    """Copy a Git file list, retaining symlinks and file metadata."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in files:
        entry = source / name
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if entry.is_symlink():
            target.symlink_to(os.readlink(entry), target_is_directory=entry.is_dir())
        else:
            shutil.copy2(entry, target)


def _file_paths(root, retain_dir=".git"):
    for entry in root.iterdir():
        if entry.name == retain_dir:
            continue
        if entry.is_dir() and not entry.is_symlink():
            for name in _file_paths(entry, retain_dir=None):
                yield Path(entry.name) / name
        else:
            yield Path(entry.name)


def _remove_selected_files(root, files):
    for name in sorted(files, key=lambda name: len(name.parts), reverse=True):
        if any((root / parent).is_symlink() or (root / parent).is_file()
               for parent in name.parents if parent != Path('.')):
            continue
        entry = root / name
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        elif entry.is_dir():
            # Never recursively delete directories containing ignored files.
            entry.rmdir()
        parent = entry.parent
        while parent != root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def _copy_all_but_one_dir(source: Path, dest: Path, retain_dir: str):
    """
    Recursively copy contents of `source` into `dest`, skipping the top-level
    entry whose name equals `retain_dir` (e.g., '.git').

    Nested entries with that name are copied because they may be Git files for
    submodules or nested worktrees.
    """
    dest.mkdir(parents=True, exist_ok=True)

    for entry in source.iterdir():
        # Also skip .git files used by linked worktrees.
        if entry.name == retain_dir:
            continue

        target = dest / entry.name

        if entry.is_symlink():
            target.symlink_to(os.readlink(entry), target_is_directory=entry.is_dir())
        elif entry.is_dir():
            # Recreate directory and recurse
            target.mkdir(exist_ok=True)
            _copy_all_but_one_dir(entry, target, retain_dir=None)
        else:
            # Copy file contents and metadata.
            shutil.copy2(entry, target)


def _remove_all_but_git_dir(root: Path):
    for entry in root.iterdir():
        if entry.name == ".git":
            continue
        if entry.is_file() or entry.is_symlink():
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry)

   


def _retry_overwrite(error):
    print(f"Could not overwrite project files: {error}", file=sys.stderr)
    while True:
        try:
            answer = input("Close any programs using these files, then [r]etry or [c]ancel (default): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if answer in ("r", "retry"):
            return True
        if answer in ("", "c", "cancel"):
            return False


def _write_result(source, destination):
    """Apply merged files, retaining a recovery copy until write or rollback succeeds."""
    existed = destination.exists()
    in_git = existed and git.is_work_tree(destination)
    remove_files = None
    if in_git:
        git.require_clean(destination)
        original_files = git.tracked_files(destination)
        result_files = set(_file_paths(source))
        # Reject collisions before touching files, including ignored paths.
        for name in result_files:
            entry = destination / name
            if name not in original_files and (entry.exists() or entry.is_symlink()):
                tracked_directory = (
                    entry.is_dir() and not entry.is_symlink()
                    and all(name / child in original_files for child in _file_paths(entry))
                )
                if not tracked_directory:
                    raise git.GitError(f'Updated file would overwrite an untracked file: {entry}')
            for parent in name.parents:
                ancestor = destination / parent
                if ancestor.is_symlink() or ancestor.is_file():
                    if parent not in original_files:
                        raise git.GitError(f'Updated file would overwrite an untracked path: {ancestor}')
        remove_files = original_files | result_files
    recovery = Path(tempfile.mkdtemp(prefix="template-update-recovery-"))
    backup = recovery / "original"
    try:
        if existed:
            if in_git:
                _copy_selected_files(destination, backup, original_files)
            else:
                shutil.copytree(destination, backup, symlinks=True,
                                ignore=shutil.ignore_patterns(".git"))
    except BaseException:
        shutil.rmtree(recovery, ignore_errors=True)
        raise

    keep_recovery = False
    try:
        while True:
            try:
                _overwrite_exclude_git_dir(source, destination, remove_files=remove_files)
                break
            except (OSError, KeyboardInterrupt) as error:
                if isinstance(error, OSError) and _retry_overwrite(error):
                    continue
                try:
                    if existed:
                        _overwrite_exclude_git_dir(backup, destination, remove_files=remove_files)
                        if in_git:
                            git.restore_work_tree(destination)
                    elif destination.exists():
                        shutil.rmtree(destination)
                except (OSError, git.GitError, KeyboardInterrupt) as restore_error:
                    keep_recovery = True
                    raise git.GitError(
                        f"Update cancelled, but restoration failed: {restore_error}\n"
                        f"Recovery copy retained at {recovery}. "
                        "Close programs using the files and restore from this copy or Git."
                    ) from restore_error
                print("Update cancelled. Original project files restored.", file=sys.stderr)
                raise SystemExit(1)
    finally:
        if not keep_recovery:
            shutil.rmtree(recovery, ignore_errors=True)


def main(argv):
    args = _parse_arguments(argv)
    try:
        with ExitStack() as resources:
            _run_update(args, resources)
    except git.DirtyRepositoryError as error:
        print(f"Warning: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except (git.GitError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except KeyboardInterrupt:
        print("Update interrupted.", file=sys.stderr)
        raise SystemExit(1)


def _run_update(args, resources):
    for directory in {args.directory.resolve(), args.output_path.resolve()}:
        if directory.exists() and git.is_work_tree(directory):
            git.require_clean(directory)

    settings_toml = args.directory / ".template_settings.toml"
    if not settings_toml.exists():
        print('Error: The project to update must contain a ".template_settings.toml" file')
        sys.exit(1)

    temp_dir = resources.enter_context(tempfile.TemporaryDirectory(ignore_cleanup_errors=True))


    print("Recreating original empty project from template...")
    project_creation_args = ["--settings-toml", str(settings_toml), "--output-path", temp_dir, "--no-gitlab-project"]
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
    resources.callback(Path(new_toml_file.name).unlink, missing_ok=True)
    project_creation_args[1] = new_toml_file.name
    other_temp_dir = resources.enter_context(tempfile.TemporaryDirectory(ignore_cleanup_errors=True))
    project_creation_args[3] = other_temp_dir
    if args.variables:
        project_creation_args.append("--variables")        
        project_creation_args.extend(args.variables)
    other_proj_dir = project_from_template.main(project_creation_args)
    new_manifest = (other_proj_dir / manifest_name).read_bytes()
    (other_proj_dir / manifest_name).unlink()
    _overwrite_exclude_git_dir(other_proj_dir, proj_dir)

    print("Commiting files to template branch...")
    git.add_all(proj_dir)
    # Either snapshot may match the baseline; empty commits are valid here.
    git.commit(proj_dir, "Update template", allow_empty=True)

    print("Checking out project branch...")
    git.checkout(proj_dir, "project")

    print("Copying project to temporary repository...")
    if git.is_work_tree(args.directory):
        _remove_all_but_git_dir(proj_dir)
        _copy_selected_files(args.directory, proj_dir, git.tracked_files(args.directory))
    else:
        _overwrite_exclude_git_dir(args.directory, proj_dir)
    (proj_dir / manifest_name).unlink(missing_ok=True)

    print("Committing existing project into temporary repository...")
    git.add_all(proj_dir)
    git.commit(proj_dir, "Update project", allow_empty=True)

    print("Merging new template into project...")
    conflicts = git.merge(proj_dir, "template")
    
    print("Copying merged repo contents into local project directory...")
    # Include refreshed provenance in the protected write so retry/rollback
    # covers it together with the merged project files.
    (proj_dir / manifest_name).write_bytes(new_manifest)
    _write_result(proj_dir, args.output_path)

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
