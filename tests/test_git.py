import pytest
import template_manager.git_wrapper as git
import os
from pathlib import Path
import shutil


@pytest.fixture
def git_repo(tmp_path_factory):
    #Copies the git repo to a temporary path, and renames the "gitdir" folder to ".git"
    oldpath = Path("tests/data/git_template")
    newpath = tmp_path_factory.mktemp("newrepo")
    shutil.copytree(oldpath, newpath, dirs_exist_ok=True)    
    os.rename(newpath / "gitdir", newpath / ".git")
    return str(newpath)

def test_merge_without_conflict(git_repo, tmp_path):
    git.clone(git_repo, tmp_path)

    newrepo = tmp_path

    git.check_out(newrepo, "ae48153")

    git.branch(newrepo, "test")

    git.checkout(newrepo, "test")

    conflicts = git.merge(newrepo, "main")

    assert conflicts == []


def test_merge_with_conflict(git_repo, tmp_path):
    git.clone(git_repo, tmp_path)

    newrepo = tmp_path

    git.check_out(newrepo, "ae48153")

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

def test_is_branch(git_repo, tmp_path):
    git.clone(git_repo, tmp_path)
    assert git.is_branch(tmp_path,"main")
    assert not git.is_branch(tmp_path,"ae48153")