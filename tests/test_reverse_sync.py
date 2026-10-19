"""Exercise extraction and checkpoint handling using real local Git history."""

import json
import subprocess
from pathlib import Path

import pytest
import toml

from template_manager import reverse_sync as sync


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args]).decode().strip()


def init(repo):
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")


def commit(repo):
    git(repo, "add", "--all")
    git(repo, "commit", "-qm", "change")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def project(tmp_path):
    template = tmp_path / "template"
    init(template)
    (template / "%project_snake%.py").write_text("initial\n")
    (template / "remove.txt").write_text("delete me\n")
    template_commit = commit(template)
    repo = tmp_path / "project"
    init(repo)
    (repo / "demo.py").write_text("initial\n")
    (repo / "remove.txt").write_text("delete me\n")
    (repo / "app.py").write_text("application\n")
    (repo / sync.SETTINGS).write_text(toml.dumps({
        "template": str(template), "git_commit": template_commit, "git_folder": ".",
        "project": "Demo", "template_syntax": "legacy", "uuid_seed": "test-seed",
    }))
    return repo, commit(repo)


def test_extract_net_diff_and_ref_lifecycle(project, tmp_path):
    repo, base = project
    sync.mark_reviewed(repo, base)
    (repo / "demo.py").write_text("infrastructure improvement\n")
    (repo / "remove.txt").unlink()
    (repo / "app.py").write_text("feature\n")
    (repo / "new.yaml").write_text("build: true\n")
    (repo / "Makefile").write_text("all:\n\techo build\n")
    target = commit(repo)
    # Dirty/untracked files must not influence a committed review batch.
    (repo / "demo.py").write_text("uncommitted\n")
    (repo / "untracked.json").write_text("{}")
    bundle = tmp_path / "bundle"
    sync.main(["-d", str(repo), "extract", "-o", str(bundle)])
    manifest = json.loads((bundle / "manifest.json").read_text())
    patch = (bundle / "changes.diff").read_text()
    assert manifest["since"] == base
    assert manifest["until"] == target
    files = {f["paths"][0]: f for f in manifest["files"]}
    assert files["demo.py"]["reasons"] == ["template-path"]
    assert files["remove.txt"]["included"]
    assert files["new.yaml"]["included"]
    assert files["Makefile"]["included"]
    assert not files["app.py"]["included"]
    assert "infrastructure improvement" in patch
    assert "deleted file" in patch
    assert "app.py" not in patch
    assert "uncommitted" not in patch
    assert "untracked" not in patch
    assert git(repo, "rev-parse", sync.DEFAULT_REF) == base
    sync.mark_reviewed(repo, target)
    assert git(repo, "rev-parse", sync.DEFAULT_REF) == target
    assert sync.extract(repo)[0] == b""
    assert (repo / "demo.py").read_text() == "uncommitted\n"


def test_missing_checkpoint_and_explicit_since(project):
    repo, base = project
    with pytest.raises(sync.ReverseSyncError, match="first use"):
        sync.extract(repo)
    assert sync.extract(repo, since=base)[0] == b""


def test_renames_globs_and_unusual_filenames(project):
    repo, base = project
    git(repo, "mv", "demo.py", "renamed.py")
    weird = "config\twith\nnewline.json"
    (repo / weird).write_text("{}\n")
    (repo / "[abc].ini").write_text("value=1\n")
    (repo / "a.ini").write_text("value=2\n")
    (repo / "app.py").write_text("feature\n")
    commit(repo)
    patch, manifest = sync.extract(repo, since=base, includes=["app.py"], excludes=["a.ini"])
    rename = next(f for f in manifest["files"] if f["status"].startswith("R"))
    assert rename["paths"] == ["demo.py", "renamed.py"]
    assert rename["included"]
    assert b"rename from demo.py" in patch
    assert b"value=1" in patch
    assert b"value=2" not in patch
    assert b"feature" in patch
    assert any(f["paths"] == [weird] for f in manifest["files"])


def test_reverts_disappear_from_net_diff(project):
    repo, base = project
    (repo / "temp.json").write_text("{}\n")
    commit(repo)
    (repo / "temp.json").unlink()
    commit(repo)
    patch, manifest = sync.extract(repo, since=base)
    assert patch == b""
    assert manifest["files"] == []


def test_ref_cannot_move_backwards_or_overwrite_branches(project):
    repo, base = project
    (repo / "app.py").write_text("new\n")
    target = commit(repo)
    sync.mark_reviewed(repo, target)
    with pytest.raises(sync.ReverseSyncError, match="ancestor"):
        sync.mark_reviewed(repo, base)
    with pytest.raises(sync.ReverseSyncError, match="refs/template-manager"):
        sync.mark_reviewed(repo, target, "refs/heads/main")
    assert git(repo, "rev-parse", sync.DEFAULT_REF) == target


def test_reject_divergent_target(project):
    repo, base = project
    (repo / "app.py").write_text("branch one\n")
    target = commit(repo)
    git(repo, "checkout", "--detach", base)
    (repo / "app.py").write_text("branch two\n")
    other = commit(repo)
    with pytest.raises(sync.ReverseSyncError, match="ancestor"):
        sync.extract(repo, until=other, since=target)


def test_template_update_uses_both_path_sets(project):
    repo, base = project
    settings = toml.loads((repo / sync.SETTINGS).read_text())
    template = Path(settings["template"])
    (template / "new_script.sh").write_text("echo hi\n")
    settings["git_commit"] = commit(template)
    (repo / sync.SETTINGS).write_text(toml.dumps(settings))
    (repo / "new_script.sh").write_text("echo hi\n")
    commit(repo)
    _, manifest = sync.extract(repo, since=base)
    assert next(f for f in manifest["files"] if f["paths"] == ["new_script.sh"])["included"]
    assert "imported template" in manifest["warnings"][-1]


def test_saved_date_binary_and_file_mode(project):
    repo, _ = project
    settings = toml.loads((repo / sync.SETTINGS).read_text())
    template = Path(settings["template"])
    (template / "%date%.sh").write_text("echo build\n")
    (template / "tool.bin").write_bytes(b"\x00before")
    settings["git_commit"] = commit(template)
    settings["date"] = "2001-02-03"
    (repo / sync.SETTINGS).write_text(toml.dumps(settings))
    script = repo / "2001-02-03.sh"
    script.write_text("echo build\n")
    (repo / "tool.bin").write_bytes(b"\x00before")
    base = commit(repo)
    script.chmod(0o755)
    (repo / "tool.bin").write_bytes(b"\x00after")
    commit(repo)
    patch, manifest = sync.extract(repo, since=base)
    assert b"old mode 100644" in patch
    assert b"new mode 100755" in patch
    assert b"Binary files" in patch
    assert all(f["included"] for f in manifest["files"])
    assert sync.extract(repo, since=base) == (patch, manifest)


def test_custom_ref_survives_push_and_fresh_clone(project, tmp_path):
    repo, base = project
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    ref = "refs/template-manager/custom/reviewed"
    sync.mark_reviewed(repo, base, ref)
    git(repo, "push", str(remote), f"{ref}:{ref}")
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "clone", "-q", str(remote), str(checkout)], check=True)
    with pytest.raises(sync.ReverseSyncError):
        sync.extract(checkout, checkpoint_ref=ref)
    git(checkout, "fetch", str(remote), f"+{ref}:{ref}")
    # The custom ref transports the commit even when no branches were pushed.
    assert sync.extract(checkout, since=ref, until=ref)[0] == b""


def test_cli_failure_does_not_create_output(project, tmp_path, capsys):
    repo, _ = project
    output = tmp_path / "missing-checkpoint-output"
    with pytest.raises(SystemExit) as exc:
        sync.main(["-d", str(repo), "extract", "-o", str(output)])
    assert exc.value.code == 1
    assert "first use" in capsys.readouterr().err
    assert not output.exists()
