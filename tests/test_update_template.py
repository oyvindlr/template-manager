import pytest
from template_manager import update_template
from pathlib import Path
import shutil
import os
import toml
import argparse
import json
import subprocess
from template_manager import project_from_template


@pytest.mark.parametrize("template_changed", [False, True])
@pytest.mark.parametrize("git_project", [False, True])
def test_update_unchanged_project(tmp_path, capsys, monkeypatch, template_changed, git_project):
    template = tmp_path / "template"
    template.mkdir()

    def run_git(*args):
        return subprocess.run(
            ["git", "-C", str(template), *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    run_git("init", "-b", "main")
    run_git("config", "user.name", "Template Test")
    run_git("config", "user.email", "test@example.com")
    (template / "content.txt").write_text("original\n")
    (template / ".gitignore").write_text("cache/\n")
    run_git("add", "--all")
    run_git("commit", "-m", "Initial template")
    args = project_from_template._parse_command_line_arguments([
        "Example", "--template", str(template), "-o", str(tmp_path / "project"),
        "--no-gitlab-project",
    ], {"default_template_repo": None, "author": None, "email": None})
    project = project_from_template._build(args)
    if git_project:
        subprocess.run(["git", "-C", str(project), "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(project), "add", "--all"], check=True)
        subprocess.run(["git", "-C", str(project), "commit", "-m", "Initial project"],
                       check=True, capture_output=True)
        (project / "cache").mkdir()
        cached_file = project / "cache" / "large-output.bin"
        cached_file.write_bytes(b"expensive build output")
        cached_stat = cached_file.stat()
        copy2 = shutil.copy2

        def copy_without_cache(source, destination, *args, **kwargs):
            assert Path(source).name != cached_file.name, "Ignored files must never be copied"
            return copy2(source, destination, *args, **kwargs)

        monkeypatch.setattr(shutil, "copy2", copy_without_cache)
    if template_changed:
        (template / "content.txt").write_text("updated\n")
        run_git("add", "--all")
        run_git("commit", "-m", "Update template")

    write_result = update_template._write_result
    writes = []

    def write_with_manifest(source, destination):
        # Provenance must be part of the recovery-protected result, rather than
        # written separately after the project's rollback copy is removed.
        manifest = (source / ".template_render_manifest.json").read_bytes()
        settings = toml.load(source / ".template_settings.toml")
        assert json.loads(manifest)["template_revision"] == settings["git_commit"]
        write_result(source, destination)
        assert (destination / ".template_render_manifest.json").read_bytes() == manifest
        writes.append(destination)

    monkeypatch.setattr(update_template, "_write_result", write_with_manifest)
    for _ in range(2):
        update_template.main(["-d", str(project)])
        assert (project / "content.txt").read_text() == (
            "updated\n" if template_changed else "original\n"
        )
        settings = toml.load(project / ".template_settings.toml")
        assert run_git("rev-parse", "HEAD").startswith(settings["git_commit"])
        assert "There were 0 merge conflicts" in capsys.readouterr().out
        if git_project:
            assert cached_file.read_bytes() == b"expensive build output"
            assert cached_file.stat().st_ino == cached_stat.st_ino
            subprocess.run(["git", "-C", str(project), "add", "--all"], check=True)
            subprocess.run(["git", "-C", str(project), "commit", "--allow-empty", "-m", "Update"],
                           check=True, capture_output=True)
    assert writes == [project, project]

@pytest.fixture
def git_test_repo_path():#PROBLEMATIC: If something goes wrong, we may end with a repo where the "gitdir" folder has been renamed to ".git"
   pathstr = "tests/data/git_template"
   path = Path(pathstr)
   os.rename(path / "gitdir", path / ".git")
   yield pathstr
   os.rename(path / ".git", path / "gitdir")

# @pytest.fixture
# def git_test_repo_path(tmp_path_factory):
#     #Copies the git repo to a temporary path, and renames the "gitdir" folder to ".git"
#     oldpath = Path("tests/data/git_template")
#     newpath = tmp_path_factory.mktemp("newrepo")
#     shutil.copytree(oldpath, newpath, dirs_exist_ok=True)    
#     os.rename(newpath / "gitdir", newpath / ".git")
#     return str(newpath)

"""
Test of private functions, delete if failing 
"""
def test_copy_overwrite_except_git_dir(tmp_path):
    source = Path("tests/data/git_template")
    dest = tmp_path
    shutil.copytree("tests/data/another_template", dest,dirs_exist_ok=True)
    os.mkdir(dest / ".git")
    (dest/".git/a_file").touch()

    update_template._overwrite_exclude_git_dir(source, dest, "gitdir")

    assert (dest/".git/a_file").exists()


    assert not (dest/"gitdir").exists()

    assert (dest/".gitignore").exists()


def test_copy_overwrite_preserves_nested_git_file(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    nested = source / "submodule"
    nested.mkdir(parents=True)
    (source / ".git").mkdir()
    (source / ".git" / "config").write_text("top-level metadata")
    (nested / ".git").write_text("gitdir: ../.git/modules/submodule\n")

    update_template._overwrite_exclude_git_dir(source, destination)

    assert not (destination / ".git").exists()
    assert (destination / "submodule" / ".git").read_text() == (
        "gitdir: ../.git/modules/submodule\n"
    )



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
    assert d["git_branch"] == "anotherbranch"


def test_branch_and_commit_correctly_set_when_updating_to_specific_branch(tmp_path, git_test_repo_path):
    shutil.copytree("tests/data/project_based_on_template", tmp_path, dirs_exist_ok=True)

    args = ["-d", str(tmp_path), "--commit", "anotherbranch"]
    
    update_template.main(args)

    d = toml.load(tmp_path / ".template_settings.toml")

    assert d["git_commit"] == "23eadff"
    assert d["git_branch"] == "anotherbranch"

def test_can_add_variables_to_updated_template(tmp_path, git_test_repo_path):
    shutil.copytree("tests/data/project_based_on_template", tmp_path, dirs_exist_ok=True)

    args = ["-d", str(tmp_path), "--variables", "VAR1:HELLO", "VAR2:WORLD"]
    
    update_template.main(args)

    d = toml.load(tmp_path / ".template_settings.toml")

    assert d["VAR1"] == "HELLO"
    assert d["VAR2"] == "WORLD"

def test_create_update_in_new_directory(tmp_path, git_test_repo_path):
    source = tmp_path / "source"
    shutil.copytree("tests/data/project_based_on_template", source)
    output = tmp_path / "output"
    args = ["-d", str(source), "--commit", "anotherbranch", "-o", str(output)]
    
    update_template.main(args)

    assert (output / ".gitignore").exists()

    
def test_create_update_in_nonexistent_directory(git_test_repo_path, tmp_path_factory):
    tmp_path = tmp_path_factory.getbasetemp() / "newdir"
    source = tmp_path_factory.mktemp("source")
    shutil.copytree("tests/data/project_based_on_template", source, dirs_exist_ok=True)
    args = ["-d", str(source), "--commit", "anotherbranch", "-o", str(tmp_path)]
    
    update_template.main(args)

    assert (tmp_path / ".gitignore").exists()
