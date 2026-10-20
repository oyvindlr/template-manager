"""Extract infrastructure candidates and explicitly manage a review checkpoint."""

import argparse
import fnmatch
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

import toml

from template_manager import project_from_template
from template_manager.git_wrapper import GitError


DEFAULT_REF = "refs/template-manager/reverse-sync/reviewed"
SETTINGS = ".template_settings.toml"
CONFIG_EXTENSIONS = {".toml", ".ini", ".yaml", ".yml", ".json", ".xml", ".cfg"}
INFRA_DIRS = {".github", ".gitlab", ".devcontainer", ".circleci"}
INFRA_NAMES = {
    ".gitignore", ".gitattributes", ".dockerignore", ".editorconfig",
    "Makefile", "GNUmakefile", "Justfile", "Jenkinsfile", "Procfile",
    "CMakeLists.txt", "setup.py", "setup.cfg", "tox.ini", "Pipfile",
    "requirements.txt", "go.mod", "go.sum", "Cargo.lock", "uv.lock",
    "poetry.lock", "yarn.lock", "Gemfile", "Gemfile.lock",
}


class ReverseSyncError(Exception):
    pass


def _git(repo, *args):
    result = subprocess.run(
        ["git", "--literal-pathspecs", "-C", str(repo), *args], capture_output=True,
    )
    if result.returncode:
        raise ReverseSyncError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def _commit(repo, revision):
    try:
        return _git(repo, "rev-parse", "--verify", "--end-of-options",
                    f"{revision}^{{commit}}").decode().strip()
    except ReverseSyncError as exc:
        raise ReverseSyncError(
            f"Cannot resolve {revision!r}. Fetch the required history and checkpoint. "
            "For first use, run 'template-reverse-sync mark-reviewed <starting-commit>'."
        ) from exc


def _ancestor(repo, before, after):
    try:
        _git(repo, "merge-base", "--is-ancestor", before, after)
    except ReverseSyncError as exc:
        raise ReverseSyncError(
            "The checkpoint must be an ancestor of the target commit; "
            "check for missing history or a rewritten branch."
        ) from exc


def _settings(repo, commit):
    return _git(repo, "show", f"{commit}:{SETTINGS}").decode("utf-8")


def _template_paths(repo, settings_text):
    """Use the existing renderer, isolated from user defaults and project output."""
    settings = toml.loads(settings_text)
    source = settings.get("template", "")
    local = repo / source
    # Older settings retained relative paths as entered from the directory in
    # which generation ran.  Projects are normally generated as a sibling of
    # their template, so support that layout while new settings store an
    # absolute source path.
    if source and not Path(source).is_absolute() and not local.exists():
        sibling = repo.parent / source
        if sibling.exists():
            local = sibling
    if local.exists():
        settings["template"] = str(local.resolve())
        if not _git_is_repo(local):
            raise ReverseSyncError("Reverse sync requires a versioned Git template.")
        if _git(local, "status", "--porcelain"):
            raise ReverseSyncError("The local template has uncommitted changes.")
    if not settings.get("git_commit") or settings["git_commit"] == "None":
        raise ReverseSyncError("Template settings must pin a git_commit for extraction.")
    # Only paths are used. Keep legacy UUID-based paths stable across runs.
    settings.setdefault("uuid_seed", "reverse-sync-legacy-paths")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings_path = root / "settings.toml"
        settings_path.write_text(toml.dumps(settings), encoding="utf-8")
        args = argparse.Namespace(
            settings_toml=settings_path, output_path=root / "rendered",
            template_syntax=None, variables=None,
        )
        rendered = project_from_template._build(
            args, render_date=settings.get("date", "1970-01-01"))
        return {
            path.relative_to(rendered).as_posix()
            for path in rendered.rglob("*") if path.is_file() or path.is_symlink()
        }


def _git_is_repo(path):
    try:
        _git(path, "rev-parse", "--git-dir")
        return True
    except ReverseSyncError:
        return False


def _reasons(path, template_paths, includes):
    file = PurePosixPath(path)
    reasons = []
    if path in template_paths:
        reasons.append("template-path")
    if file.suffix.lower() in CONFIG_EXTENSIONS:
        reasons.append("configuration-extension")
    if (file.parts[0] in INFRA_DIRS or file.name in INFRA_NAMES
            or file.name.startswith(("Dockerfile", "Containerfile", "requirements"))):
        reasons.append("infrastructure-path")
    if any(fnmatch.fnmatchcase(path, pattern) for pattern in includes):
        reasons.append("explicit-include")
    return reasons


def extract(repo, until="HEAD", checkpoint_ref=DEFAULT_REF, since=None,
            includes=(), excludes=()):
    repo = Path(_git(repo, "rev-parse", "--show-toplevel").decode().strip())
    before = _commit(repo, since or checkpoint_ref)
    after = _commit(repo, until)
    _ancestor(repo, before, after)
    old_settings, new_settings = _settings(repo, before), _settings(repo, after)
    template_paths = _template_paths(repo, old_settings)
    if old_settings != new_settings:
        template_paths |= _template_paths(repo, new_settings)
    # NUL records handle spaces, tabs and newlines in Git filenames.
    records = _git(repo, "diff", "--name-status", "-z", "--find-renames",
                   before, after, "--").split(b"\0")
    files = []
    index = 0
    while index < len(records) - 1:
        status = records[index].decode("ascii")
        count = 2 if status.startswith("R") else 1
        paths = [p.decode("utf-8", errors="surrogateescape")
                 for p in records[index + 1:index + count + 1]]
        index += count + 1
        reasons = sorted({reason for path in paths
                          for reason in _reasons(path, template_paths, includes)})
        excluded = any(fnmatch.fnmatchcase(path, pattern)
                       for path in paths for pattern in excludes)
        if excluded:
            reasons = ["explicit-exclude"]
        included = bool(reasons) and not excluded
        files.append({"status": status, "paths": paths, "included": included,
                      "reasons": reasons or ["no-rule-matched"]})
    # One diff per selected change avoids command-line length limits. Rename pairs
    # stay together, including moves out of a template/infrastructure path.
    patch = b"".join(
        _git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-color",
             "--find-renames", "--src-prefix=a/", "--dst-prefix=b/",
             before, after, "--", *file["paths"])
        for file in files if file["included"]
    )
    warnings = [
        "Selection is heuristic; excluded paths may contain reusable infrastructure.",
        "Rendering uses the installed template-manager version and saved date/UUID seed. "
        "Missing date or UUID seed uses a fixed fallback for path selection; "
        "historical paths containing those values may not match.",
    ]
    if old_settings != new_settings:
        warnings.append("Template settings changed in this range; imported template "
                        "updates are not subtracted from the diff.")
    return patch, {"schema_version": 1, "checkpoint_ref": checkpoint_ref,
                   "since": before, "until": after, "files": files,
                   "warnings": warnings}


def mark_reviewed(repo, revision, checkpoint_ref=DEFAULT_REF):
    if not checkpoint_ref.startswith("refs/template-manager/"):
        raise ReverseSyncError("Checkpoint refs must be under refs/template-manager/.")
    _git(repo, "check-ref-format", checkpoint_ref)
    target = _commit(repo, revision)
    # An empty old value asks update-ref to require that the ref does not exist.
    existing = next((line.split()[0] for line in
                     _git(repo, "for-each-ref", "--format=%(objectname) %(refname)",
                          checkpoint_ref).decode().splitlines()
                     if line.split()[1] == checkpoint_ref), "")
    if existing:
        _ancestor(repo, existing, target)
    _git(repo, "update-ref", checkpoint_ref, target, existing)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-d", "--directory", type=Path, default=Path("."))
    parser.add_argument("--checkpoint-ref", default=DEFAULT_REF)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("extract", help="Write a review bundle; do not advance the ref")
    scan.add_argument("--since", help="Override the checkpoint for this extraction")
    scan.add_argument("--until", default="HEAD")
    scan.add_argument("-o", "--output-path", type=Path, default=Path("reverse-sync-output"))
    scan.add_argument("--include", action="append", default=[], help="Include a path glob")
    scan.add_argument("--exclude", action="append", default=[], help="Exclude a path glob (takes priority)")
    mark = commands.add_parser("mark-reviewed", help="Explicitly update the local checkpoint ref")
    mark.add_argument("commit", help="Exact commit reviewed, normally manifest.json's until SHA")
    args = parser.parse_args(argv)
    try:
        if args.command == "mark-reviewed":
            target = mark_reviewed(args.directory, args.commit, args.checkpoint_ref)
            print(f"{args.checkpoint_ref} -> {target} (local ref only)")
        else:
            patch, manifest = extract(args.directory, args.until, args.checkpoint_ref,
                                      args.since, args.include, args.exclude)
            args.output_path.mkdir(parents=True, exist_ok=True)
            (args.output_path / "changes.diff").write_bytes(patch)
            (args.output_path / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            count = sum(file["included"] for file in manifest["files"])
            print(f"Selected {count} of {len(manifest['files'])} changes; "
                  f"bundle: {args.output_path}. Checkpoint unchanged.")
    except (ReverseSyncError, GitError, project_from_template.TemplateError,
            OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


def entry_point():
    main(sys.argv[1:])


if __name__ == "__main__":
    entry_point()
