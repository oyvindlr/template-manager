"""Extract infrastructure candidates and explicitly manage a review checkpoint."""

import argparse
import fnmatch
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

import toml

from template_manager import __version__
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
MAX_REPORTED_COMMITS = 50


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


def _optional_commit(repo, revision):
    try:
        return _commit(repo, revision)
    except ReverseSyncError:
        return None


def _optional_ref_commit(repo, ref):
    result = subprocess.run(
        ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", ref],
        capture_output=True,
    )
    if result.returncode == 1:
        return None
    return _commit(repo, ref)


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


def _commit_info(repo, commit):
    fields = _git(repo, "show", "-s", "--format=%H%x00%aI%x00%s", commit).decode(
        "utf-8", errors="replace").split("\0", 2)
    return {"sha": fields[0], "date": fields[1], "subject": fields[2].rstrip()}


def _first_merge_after_template_baseline(repo, until):
    settings_commits = _git(
        repo, "rev-list", "--reverse", until, "--", SETTINGS
    ).decode().splitlines()
    if not settings_commits:
        raise ReverseSyncError(
            f"Cannot identify a template baseline because {SETTINGS} is absent from history."
        )
    template_baseline = settings_commits[0]
    merges = _git(
        repo, "rev-list", "--reverse", "--ancestry-path", "--merges",
        f"{template_baseline}..{until}",
    ).decode().splitlines()
    if not merges:
        raise ReverseSyncError(
            "Cannot identify a first merge after the template baseline. "
            "Pass --since explicitly."
        )
    return merges[0], template_baseline


def _resolve_review_since(repo, until, checkpoint_ref, since, strategy):
    if since:
        return _commit(repo, since), {"kind": "explicit", "value": since}
    checkpoint = _optional_ref_commit(repo, checkpoint_ref)
    if checkpoint:
        return checkpoint, {"kind": "checkpoint", "value": checkpoint_ref}
    if strategy == "first-merge-after-template-baseline":
        baseline, template_baseline = _first_merge_after_template_baseline(repo, until)
        return baseline, {
            "kind": strategy,
            "template_baseline": template_baseline,
        }
    raise ReverseSyncError(
        "No checkpoint exists. Pass --since or select a supported --since-strategy."
    )


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


def _classification_hint(file):
    reasons = set(file["reasons"])
    if "explicit-exclude" in reasons:
        return "excluded"
    if reasons & {"template-path", "infrastructure-path", "explicit-include"}:
        return "likely-template-relevant"
    if "configuration-extension" in reasons:
        return "ambiguous"
    return "likely-project-specific"


def _diff_stats(repo, before, after, paths):
    output = _git(repo, "diff", "--numstat", "-z", "--find-renames",
                  before, after, "--", *paths)
    fields = output.split(b"\0", 1)[0].split(b"\t", 2)
    if len(fields) < 2:
        return {"additions": 0, "deletions": 0, "binary": False}
    added, deleted = fields[:2]
    binary = added == b"-" or deleted == b"-"
    return {
        "additions": 0 if binary else int(added),
        "deletions": 0 if binary else int(deleted),
        "binary": binary,
    }


def _repo_status(repo):
    status = _git(repo, "status", "--short", "--branch").decode(
        "utf-8", errors="surrogateescape").splitlines()
    return {"clean": len(status) <= 1, "lines": status}


def _template_base_state(repo, settings, base):
    source = settings.get("template", "")
    local = repo / source
    if source and not Path(source).is_absolute() and not local.exists():
        sibling = repo.parent / source
        if sibling.exists():
            local = sibling
    if local.exists() and _git_is_repo(local):
        sha = _optional_commit(local, base)
        return {
            "name": base,
            "status": "resolved" if sha else "not-found",
            "sha": sha,
            "source": str(local.resolve()),
            "repository_status": _repo_status(local),
        }
    if not source:
        return {
            "name": base, "status": "error", "sha": None, "source": source,
            "error": "Template settings do not specify a template source.",
        }
    result = subprocess.run(
        ["git", "ls-remote", source, base, f"refs/heads/{base}"],
        capture_output=True,
    )
    if result.returncode:
        return {
            "name": base,
            "status": "error",
            "sha": None,
            "source": source,
            "error": result.stderr.decode(errors="replace").strip(),
        }
    lines = result.stdout.decode().splitlines()
    return {
        "name": base,
        "status": "resolved" if lines else "not-found",
        "sha": lines[0].split()[0] if lines else None,
        "source": source,
    }


def _template_summary(settings):
    return {
        "source": settings.get("template"),
        "revision": settings.get("git_commit"),
        "subdirectory": settings.get("git_folder", "."),
        "syntax": settings.get("template_syntax", "auto"),
    }


def _remote_checkpoint(repo, remote, checkpoint_ref):
    if not remote:
        return {"remote": None, "status": "not-checked", "sha": None}
    result = subprocess.run(
        ["git", "--literal-pathspecs", "-C", str(repo), "ls-remote",
         "--refs", remote, checkpoint_ref],
        capture_output=True,
    )
    if result.returncode:
        return {
            "remote": remote,
            "status": "error",
            "sha": None,
            "error": result.stderr.decode(errors="replace").strip(),
        }
    line = result.stdout.decode().strip()
    return {
        "remote": remote,
        "status": "present" if line else "absent",
        "sha": line.split()[0] if line else None,
    }


def _review_markdown(report):
    rows = []
    for file in report["files"]:
        paths = " -> ".join(file["paths"])
        paths = paths.replace("|", "\\|").replace("`", "\\`")
        paths = paths.replace("\t", "\\t").replace("\n", "\\n")
        stats = "binary" if file["stats"]["binary"] else (
            f"+{file['stats']['additions']}/-{file['stats']['deletions']}")
        rows.append(
            f"| `{paths}` | {file['status']} | "
            f"{'yes' if file['included'] else 'no'} | "
            f"{file['classification_hint']} | "
            f"{', '.join(file['reasons'])} | {stats} |"
        )
    checkpoint = report["checkpoint"]
    remote = checkpoint["remote"]
    baseline = report["baseline_source"]
    baseline_detail = (
        f" (template baseline `{baseline['template_baseline']}`)"
        if baseline.get("template_baseline") else "")
    warnings = [
        "## Warnings", "",
        *[f"- {warning}" for warning in report["warnings"]],
        "",
    ] if report["warnings"] else []
    return "\n".join([
        "# Reverse-sync review",
        "",
        f"- Tool version: `{report['tool_version']}`",
        f"- Project: `{report['project']['path']}`",
        f"- Project worktree: "
        f"`{'clean' if report['project']['status']['clean'] else 'dirty'}`",
        f"- Range: `{report['since']}`..`{report['until']}`",
        f"- Baseline source: `{baseline['kind']}`{baseline_detail}",
        f"- Local checkpoint: `{checkpoint['local'] or 'absent'}`",
        f"- Remote checkpoint ({remote['remote'] or 'not checked'}): "
        f"`{remote['sha'] or remote['status']}`",
        f"- Template: `{report['template']['source']}` at "
        f"`{report['template']['revision']}` "
        f"(subdirectory `{report['template']['subdirectory']}`)",
        f"- Intended template base: `{report['template']['current_base']['name']}` "
        f"at `{report['template']['current_base']['sha'] or report['template']['current_base']['status']}`",
        f"- Included candidates: {report['summary']['included']} of "
        f"{report['summary']['changed_files']}",
        "",
        "| Path | Status | Candidate | Hint | Reasons | Diff |",
        "|---|---:|---:|---|---|---:|",
        *rows,
        "",
        *warnings,
        "## Suggested next steps",
        "",
        "1. Start with `likely-template-relevant` and `ambiguous` entries.",
        "2. Use `changes.diff` for selected candidates and `all-changes.diff` only "
        "when an excluded entry needs inspection.",
        "3. Adapt accepted changes to the current template, render the patched "
        "template with source and alternate values, then run one targeted check.",
        "4. Update the checkpoint only after every entry has a disposition.",
        "",
    ]) + "\n"


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


def review(repo, until="HEAD", checkpoint_ref=DEFAULT_REF, since=None,
           since_strategy="first-merge-after-template-baseline", includes=(),
           excludes=(), remote="origin", template_base="main"):
    repo = Path(_git(repo, "rev-parse", "--show-toplevel").decode().strip())
    after = _commit(repo, until)
    before, baseline_source = _resolve_review_since(
        repo, after, checkpoint_ref, since, since_strategy)
    patch, report = extract(
        repo, after, checkpoint_ref, before, includes, excludes)
    all_patch = _git(
        repo, "diff", "--no-ext-diff", "--no-textconv", "--no-color",
        "--find-renames", "--src-prefix=a/", "--dst-prefix=b/",
        before, after, "--",
    )
    for file in report["files"]:
        file["stats"] = _diff_stats(repo, before, after, file["paths"])
        file["classification_hint"] = _classification_hint(file)
        file["template_path_hint"] = (
            file["paths"][-1]
            if "template-path" in file["reasons"] else None
        )
    previous_settings = toml.loads(_settings(repo, before))
    settings = toml.loads(_settings(repo, after))
    commit_shas = _git(
        repo, "rev-list", "--reverse", f"{before}..{after}"
    ).decode().splitlines()
    reported_shas = commit_shas[:MAX_REPORTED_COMMITS]
    commits = [
        _commit_info(repo, commit)
        for commit in reported_shas
    ]
    local_checkpoint = _optional_ref_commit(repo, checkpoint_ref)
    report.update({
        "schema_version": 2,
        "tool_version": __version__.strip(),
        "baseline_source": baseline_source,
        "project": {
            "path": str(repo),
            "head": _commit(repo, "HEAD"),
            "status": _repo_status(repo),
        },
        "template": {
            **_template_summary(settings),
            "previous": (
                _template_summary(previous_settings)
                if previous_settings != settings else None
            ),
            "parameter_names": sorted(settings),
            "current_base": _template_base_state(repo, settings, template_base),
        },
        "checkpoint": {
            "ref": checkpoint_ref,
            "local": local_checkpoint,
            "remote": _remote_checkpoint(repo, remote, checkpoint_ref),
        },
        "commits": commits,
        "summary": {
            "changed_files": len(report["files"]),
            "included": sum(file["included"] for file in report["files"]),
            "commits": len(commit_shas),
            "reported_commits": len(commits),
        },
        "artifacts": {
            "selected_diff": "changes.diff",
            "all_diff": "all-changes.diff",
            "json": "review.json",
            "markdown": "review.md",
        },
    })
    if len(commit_shas) > len(commits):
        report["warnings"].append(
            f"Commit details are limited to the first {MAX_REPORTED_COMMITS} "
            f"of {len(commit_shas)} commits in the range.")
    return patch, all_patch, report


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
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__.strip()}")
    parser.add_argument("-d", "--directory", type=Path, default=Path("."))
    parser.add_argument("--checkpoint-ref", default=DEFAULT_REF)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("extract", help="Write a review bundle; do not advance the ref")
    scan.add_argument("--since", help="Override the checkpoint for this extraction")
    scan.add_argument("--until", default="HEAD")
    scan.add_argument("-o", "--output-path", type=Path, default=Path("reverse-sync-output"))
    scan.add_argument("--include", action="append", default=[], help="Include a path glob")
    scan.add_argument("--exclude", action="append", default=[], help="Exclude a path glob (takes priority)")
    review_parser = commands.add_parser(
        "review", help="Write a review-ready bundle; do not advance the ref")
    review_parser.add_argument(
        "--since", help="Override the checkpoint or automatic baseline")
    review_parser.add_argument(
        "--since-strategy",
        choices=["first-merge-after-template-baseline"],
        default="first-merge-after-template-baseline",
        help="Fallback used when no checkpoint exists")
    review_parser.add_argument("--until", default="HEAD")
    review_parser.add_argument(
        "-o", "--output-path", type=Path, default=Path("reverse-sync-review"))
    review_parser.add_argument("--include", action="append", default=[],
                               help="Include a path glob")
    review_parser.add_argument("--exclude", action="append", default=[],
                               help="Exclude a path glob (takes priority)")
    review_parser.add_argument(
        "--remote", default="origin",
        help="Project remote used only to report checkpoint state; empty disables")
    review_parser.add_argument(
        "--template-base", default="main",
        help="Intended template pull-request base to resolve and report")
    mark = commands.add_parser("mark-reviewed", help="Explicitly update the local checkpoint ref")
    mark.add_argument("commit", help="Exact commit reviewed, normally manifest.json's until SHA")
    args = parser.parse_args(argv)
    try:
        if args.command == "mark-reviewed":
            target = mark_reviewed(args.directory, args.commit, args.checkpoint_ref)
            print(f"{args.checkpoint_ref} -> {target} (local ref only)")
        elif args.command == "extract":
            patch, manifest = extract(args.directory, args.until, args.checkpoint_ref,
                                      args.since, args.include, args.exclude)
            args.output_path.mkdir(parents=True, exist_ok=True)
            (args.output_path / "changes.diff").write_bytes(patch)
            (args.output_path / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            count = sum(file["included"] for file in manifest["files"])
            print(f"Selected {count} of {len(manifest['files'])} changes; "
                  f"bundle: {args.output_path}. Checkpoint unchanged.")
        else:
            patch, all_patch, report = review(
                args.directory, args.until, args.checkpoint_ref, args.since,
                args.since_strategy, args.include, args.exclude,
                args.remote or None, args.template_base)
            args.output_path.mkdir(parents=True, exist_ok=True)
            (args.output_path / "changes.diff").write_bytes(patch)
            (args.output_path / "all-changes.diff").write_bytes(all_patch)
            (args.output_path / "review.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8")
            (args.output_path / "review.md").write_text(
                _review_markdown(report), encoding="utf-8")
            print(
                f"Prepared {report['summary']['included']} of "
                f"{report['summary']['changed_files']} changes for review; "
                f"bundle: {args.output_path}. Checkpoint unchanged.")
    except (ReverseSyncError, GitError, project_from_template.TemplateError,
            OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


def entry_point():
    main(sys.argv[1:])


if __name__ == "__main__":
    entry_point()
