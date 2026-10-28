from pathlib import Path
import shutil
import subprocess

import pytest

from template_manager import git_wrapper as git, update_template as update


def run_git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    run_git(project, "init", "-b", "main")
    run_git(project, "config", "user.name", "Test")
    run_git(project, "config", "user.email", "test@example.com")
    (project / "original.txt").write_text("original")
    (project / ".gitignore").write_text("ignored.txt\n")
    (project / ".template_settings.toml").write_text('template = "unused"\n')
    run_git(project, "add", "--all")
    run_git(project, "commit", "-m", "Initial project")
    return project


@pytest.fixture
def merged(tmp_path):
    merged = tmp_path / "merged"
    merged.mkdir()
    (merged / "new.txt").write_text("updated")
    return merged


@pytest.mark.parametrize("dirty", ["tracked", "staged", "untracked"])
@pytest.mark.parametrize("separate_output", [False, True])
def test_dirty_repo_exits_before_generation(project, tmp_path, monkeypatch, capsys,
                                          dirty, separate_output):
    if dirty == "untracked":
        (project / "untracked.txt").write_text("keep")
    else:
        (project / "original.txt").write_text("keep")
        if dirty == "staged":
            run_git(project, "add", "--all")
    before = run_git(project, "status", "--porcelain")
    monkeypatch.setattr(update.project_from_template, "main",
                        lambda *a: pytest.fail("Generation must not start"))
    args = ["-d", str(project)]
    if separate_output:
        args += ["-o", str(tmp_path / "output")]
    with pytest.raises(SystemExit) as error:
        update.main(args)
    assert error.value.code == 1
    assert "Commit or stash" in capsys.readouterr().err
    assert run_git(project, "status", "--porcelain") == before


def test_dirty_output_repo_is_also_rejected(project, tmp_path, capsys):
    source = tmp_path / "source"
    source.mkdir()
    (project / "untracked.txt").write_text("keep")
    with pytest.raises(SystemExit):
        update.main(["-d", str(source), "-o", str(project)])
    assert "uncommitted changes" in capsys.readouterr().err


def fail_first_overwrite(monkeypatch):
    real_overwrite = update._overwrite_exclude_git_dir
    calls = []

    def overwrite(source, dest, **kwargs):
        calls.append(source)
        if len(calls) == 1:
            (dest / "original.txt").unlink()
            (dest / "new.txt").write_text("partial update")
            raise PermissionError("file is locked")
        real_overwrite(source, dest, **kwargs)

    monkeypatch.setattr(update, "_overwrite_exclude_git_dir", overwrite)
    return calls


def test_retry_after_partial_overwrite(project, merged, monkeypatch, capsys):
    head = run_git(project, "rev-parse", "HEAD")
    calls = fail_first_overwrite(monkeypatch)
    answers = iter(["invalid", "retry"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    update._write_result(merged, project)
    assert len(calls) == 2
    assert (project / "new.txt").read_text() == "updated"
    assert run_git(project, "rev-parse", "HEAD") == head
    assert "file is locked" in capsys.readouterr().err


@pytest.mark.parametrize("answer", ["cancel", EOFError(), KeyboardInterrupt()])
def test_cancel_restores_git_and_ignored_files(project, merged, monkeypatch, capsys, answer):
    (project / "ignored.txt").write_text("keep ignored file")
    head = run_git(project, "rev-parse", "HEAD")
    fail_first_overwrite(monkeypatch)

    def respond(_):
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr("builtins.input", respond)
    restore = git.restore_work_tree
    restored = []
    monkeypatch.setattr(git, "restore_work_tree", lambda path: (restored.append(path), restore(path)))
    with pytest.raises(SystemExit) as error:
        update._write_result(merged, project)
    assert error.value.code == 1
    assert restored == [project]
    assert (project / "original.txt").read_text() == "original"
    assert (project / "ignored.txt").read_text() == "keep ignored file"
    assert not (project / "new.txt").exists()
    assert run_git(project, "status", "--porcelain") == ""
    assert run_git(project, "rev-parse", "HEAD") == head
    assert "Original project files restored" in capsys.readouterr().err


def test_success_leaves_ignored_files_in_place(project, merged, monkeypatch):
    ignored = project / "ignored.txt"
    ignored.write_text("keep")
    before = ignored.stat()
    copy2 = shutil.copy2

    def copy_tracked_only(source, dest, *args, **kwargs):
        assert Path(source) != ignored
        return copy2(source, dest, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", copy_tracked_only)
    update._write_result(merged, project)
    assert ignored.read_text() == "keep"
    assert ignored.stat().st_ino == before.st_ino
    assert not (project / "original.txt").exists()


def test_new_template_file_cannot_overwrite_ignored_file(project, merged):
    (project / "ignored.txt").write_text("keep")
    (merged / "ignored.txt").write_text("new template file")
    with pytest.raises(git.GitError, match="overwrite an untracked file"):
        update._write_result(merged, project)
    assert (project / "ignored.txt").read_text() == "keep"
    assert (project / "original.txt").read_text() == "original"


@pytest.mark.parametrize("location", ["root", "subfolder", "worktree"])
def test_copy_only_tracked_files(project, tmp_path, location):
    source = project
    if location == "subfolder":
        source = project / "subfolder"
        source.mkdir()
    elif location == "worktree":
        source = tmp_path / "worktree"
        run_git(project, "worktree", "add", "-b", "copy-test", str(source))
    unusual_name = "spaces and\nnewline.txt"
    (source / unusual_name).write_text("tracked")
    (source / "link").symlink_to(unusual_name)
    (source / "ignored.txt").write_text("tracked despite ignore rule")
    run_git(source, "add", "--force", "--", unusual_name, "link", "ignored.txt")
    run_git(source, "commit", "-m", "Add tracked files")
    (source / "untracked.txt").write_text("do not copy")
    (source / "cache").mkdir()
    (source / "cache" / "output.bin").write_text("do not copy")

    destination = tmp_path / "snapshot"
    update._copy_selected_files(source, destination, git.tracked_files(source))

    assert (destination / unusual_name).read_text() == "tracked"
    assert (destination / "link").is_symlink()
    assert (destination / "link").readlink() == Path(unusual_name)
    assert (destination / "ignored.txt").read_text() == "tracked despite ignore rule"
    assert not (destination / "untracked.txt").exists()
    assert not (destination / "cache").exists()
    assert not (destination / ".git").exists()
    if location == "subfolder":
        assert not (destination / "original.txt").exists()


def test_copy_tracked_files_skips_uninitialized_submodule(project, tmp_path):
    submodule = tmp_path / "submodule"
    submodule.mkdir()
    run_git(submodule, "init", "-b", "main")
    run_git(submodule, "config", "user.name", "Test")
    run_git(submodule, "config", "user.email", "test@example.com")
    (submodule / "content.txt").write_text("submodule content")
    run_git(submodule, "add", "--all")
    run_git(submodule, "commit", "-m", "Initial submodule")
    subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "-C", str(project),
         "submodule", "add", str(submodule), "module"],
        check=True, capture_output=True, text=True,
    )
    run_git(project, "commit", "-m", "Add submodule")
    run_git(project, "submodule", "deinit", "--force", "module")

    files = git.tracked_files(project)
    destination = tmp_path / "snapshot"
    update._copy_selected_files(project, destination, files)

    assert Path("module") not in files
    assert not (destination / "module").exists()
    assert (destination / ".gitmodules").is_file()


@pytest.mark.parametrize("old_is_directory", [False, True])
def test_update_can_change_file_to_directory(project, merged, old_is_directory):
    old = project / "changing"
    new = merged / "changing"
    if old_is_directory:
        old.mkdir()
        (old / "nested.txt").write_text("old")
        new.write_text("new")
    else:
        old.write_text("old")
        new.mkdir()
        (new / "nested.txt").write_text("new")
    run_git(project, "add", "--all")
    run_git(project, "commit", "-m", "Add changing path")
    update._write_result(merged, project)
    assert (new if new.is_file() else new / "nested.txt").read_text() == "new"
    assert (old if old.is_file() else old / "nested.txt").read_text() == "new"


def test_failed_rollback_retains_recovery(project, merged, tmp_path, monkeypatch):
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    monkeypatch.setattr(update.tempfile, "mkdtemp", lambda **kw: str(recovery))

    def fail(source, dest, **kwargs):
        (dest / "original.txt").write_text("partial")
        raise PermissionError("still locked")

    monkeypatch.setattr(update, "_overwrite_exclude_git_dir", fail)
    monkeypatch.setattr("builtins.input", lambda _: "cancel")
    with pytest.raises(git.GitError, match="Recovery copy retained"):
        update._write_result(merged, project)
    assert (recovery / "original" / "original.txt").read_text() == "original"


def test_cancel_restores_non_git_folder(tmp_path, merged, monkeypatch):
    destination = tmp_path / "output"
    destination.mkdir()
    (destination / "original.txt").write_text("original")
    fail_first_overwrite(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "c")
    with pytest.raises(SystemExit):
        update._write_result(merged, destination)
    assert list(destination.iterdir()) == [destination / "original.txt"]
    assert (destination / "original.txt").read_text() == "original"


def test_cancel_removes_new_output_folder(tmp_path, merged, monkeypatch):
    destination = tmp_path / "new-output"

    def fail(source, dest, **kwargs):
        dest.mkdir()
        (dest / "partial.txt").write_text("partial")
        raise PermissionError("locked")

    monkeypatch.setattr(update, "_overwrite_exclude_git_dir", fail)
    monkeypatch.setattr("builtins.input", lambda _: "c")
    with pytest.raises(SystemExit):
        update._write_result(merged, destination)
    assert not destination.exists()


def test_linked_worktree_git_file_survives_update(project, merged, tmp_path):
    worktree = tmp_path / "worktree"
    run_git(project, "worktree", "add", "-b", "update-test", str(worktree))
    metadata = (worktree / ".git").read_text()
    update._write_result(merged, worktree)
    assert (worktree / ".git").read_text() == metadata
    assert (worktree / "new.txt").read_text() == "updated"
    assert git.is_work_tree(worktree)


def test_git_restore_only_changes_target_subfolder(project):
    subfolder = project / "subfolder"
    subfolder.mkdir()
    (subfolder / "file.txt").write_text("original")
    run_git(project, "add", "--all")
    run_git(project, "commit", "-m", "Add subfolder")
    (subfolder / "file.txt").write_text("changed")
    (project / "original.txt").write_text("outside")
    git.restore_work_tree(subfolder)
    assert (subfolder / "file.txt").read_text() == "original"
    assert (project / "original.txt").read_text() == "outside"


def test_directory_delete_failure_is_not_swallowed(tmp_path, monkeypatch):
    (tmp_path / "folder").mkdir()

    def fail(*a, **kw):
        raise PermissionError("locked folder")

    monkeypatch.setattr(shutil, "rmtree", fail)
    with pytest.raises(PermissionError):
        update._remove_all_but_git_dir(tmp_path)


@pytest.mark.parametrize("error", [git.GitError("git failed"), OSError("disk full"),
                                  ValueError("invalid settings")])
def test_expected_errors_have_readable_message(monkeypatch, capsys, error):
    def fail(*a):
        raise error

    monkeypatch.setattr(update, "_run_update", fail)
    with pytest.raises(SystemExit) as result:
        update.main([])
    assert result.value.code == 1
    assert str(error) in capsys.readouterr().err


def test_merge_failure_without_conflicts_is_error(project, monkeypatch):
    real_run = subprocess.run

    def run(command, **kw):
        if "merge" in command:
            return subprocess.CompletedProcess(command, 1, "", "merge failed")
        return real_run(command, **kw)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(git.GitError, match="merge failed"):
        git.merge(project, "missing")
