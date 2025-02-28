import pytest
from template_generator import update_template
from pathlib import Path
import shutil
import os
import toml
import argparse

@pytest.fixture
def git_test_repo_path():#PROBLEMATIC: If something goes wrong, we may end with a repo where the "gitdir" folder has been renamed to ".git"
    pathstr = "tests/data/git_template"
    path = Path(pathstr)
    os.rename(path / "gitdir", path / ".git")
    yield pathstr
    os.rename(path / ".git", path / "gitdir")


"""
Test of private functions, delete if failing 
"""
def test_copy_overwrite_except_git_dir(tmp_path):
    source = Path("tests/data/git_template")
    dest = tmp_path
    shutil.copytree("tests/data/my_template", dest,dirs_exist_ok=True)
    os.mkdir(dest / ".git")
    (dest/".git/a_file").touch()

    update_template._overwrite_exclude_git_dir(source, dest, "gitdir")

    assert (dest/".git/a_file").exists()


    assert not (dest/"gitdir").exists()

    assert (dest/"%project%-file.txt").exists()

    assert not (dest/"jau.txt").exists()


def test_toml_file_update_hash():
    
    new_toml = update_template._toml_file_with_updated_commit_hash("tests/data/.template_settings.toml", "abcdef0")

    d = toml.load(new_toml.name)

    assert d["description"] == "A description"
    assert d["git_commit"] == "abcdef0"

"""
Test of api
"""
def test_update_template(tmp_path, git_test_repo_path):
    shutil.copytree("tests/data/project_based_on_template", tmp_path, dirs_exist_ok=True)

    args = ["-d", str(tmp_path)]
    
    update_template.main(args)

    assert (tmp_path / "project-based-on-template-file.txt").exists()

    assert (tmp_path / ".gitignore").read_text() == "something"

    assert (tmp_path / ".template_settings.toml").exists()

    d = toml.load(tmp_path / ".template_settings.toml")

    assert d["git_commit"] == "078b406"
    assert d["template"] == "tests/data/git_template"


def test_update_template_with_conflicts(tmp_path, git_test_repo_path, capsys):
    shutil.copytree("tests/data/project_based_on_template", tmp_path, dirs_exist_ok=True)

    (tmp_path / "project-based-on-template-file.txt").write_text("Hello")

    args = ["-d", str(tmp_path)]
    
    update_template.main(args)

    out = capsys.readouterr().out
    assert out.find("conflicts") >= 0
    assert out.find("project-based-on-template-file.txt") >= 0

def test_updates_to_most_recent_commit_in_specific_branch(tmp_path, git_test_repo_path):
    shutil.copytree("tests/data/project_based_on_template_in_another_branch", tmp_path, dirs_exist_ok=True)

    args = ["-d", str(tmp_path)]
    
    update_template.main(args)

    d = toml.load(tmp_path / ".template_settings.toml")

    assert d["git_commit"] == "23eadff"