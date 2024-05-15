import pytest
import template_generator.git_wrapper as git
import os
from pathlib import Path

@pytest.fixture
def git_repo():#PROBLEMATIC: If something goes wrong, we may end with a repo where the "gitdir" folder has been renamed to ".git"
    pathstr = "tests/data/git_template"
    path = Path(pathstr)
    os.rename(path / "gitdir", path / ".git")
    yield pathstr
    os.rename(path / ".git", path / "gitdir")

def test_merge_without_conflict(git_repo, tmp_path):
    git.clone(git_repo, tmp_path)

    newrepo = tmp_path

    git.check_out_commit(newrepo, "ae48153")

    git.branch(newrepo, "test")

    git.checkout(newrepo, "test")

    conflicts = git.merge(newrepo, "main")

    assert conflicts == []


def test_merge_with_conflict(git_repo, tmp_path):
    git.clone(git_repo, tmp_path)

    newrepo = tmp_path

    git.check_out_commit(newrepo, "ae48153")

    git.branch(newrepo, "test")
    git.checkout(newrepo, "test")

    (newrepo / "%project%-file.txt").write_text("Hallo")
    (newrepo / ".gitignore").write_text("Hei")

    git.add_all(newrepo)
    git.commit(newrepo, "Hlleo")

    conflicts = git.merge(newrepo, "main")

    assert "%project%-file.txt" in conflicts
    assert len(conflicts) == 1

def test_merge_other_error():
    with pytest.raises(git.GitError):
        git.merge("nonexistent_repo", "nonexisting_branch")