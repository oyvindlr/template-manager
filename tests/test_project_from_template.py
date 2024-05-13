import pytest
import argparse
from template_generator import project_from_template
from template_generator.project_from_template import TemplateError
from pathlib import Path
import toml
import os
import shutil
import sys
import subprocess

@pytest.fixture
def git_test_repo_path(tmp_path_factory):
    oldpath = Path("tests/data/git_template")
    newpath = tmp_path_factory.mktemp("newrepo")
    shutil.copytree(oldpath, newpath, dirs_exist_ok=True)    
    os.rename(newpath / "gitdir", newpath / ".git")
    return str(newpath)
    
@pytest.fixture
def git_test_repo_direct_path(): #PROBLEMATIC: If something goes wrong, we may end with a repo where the "gitdir" folder has been renamed to ".git"
    pathstr = "tests/data/git_template"
    path = Path(pathstr)
    os.rename(path / "gitdir", path / ".git")
    yield pathstr
    os.rename(path / ".git", path / "gitdir")

@pytest.fixture
def another_template_path(tmp_path_factory):
    oldpath = Path("./tests/data/another_template")
    newpath = tmp_path_factory.mktemp("templatecopy")
    shutil.copytree(oldpath, newpath, dirs_exist_ok=True) 
    return str(newpath)


@pytest.fixture
def defaultargs(tmp_path):
    args = argparse.Namespace()
    args.template = None
    args.output_path = tmp_path
    args.project = "MyTestProject"
    args.description = "A description"
    args.author = "Me A. Person"
    args.email = "me@person.edu"
    args.variables = ["HEI:HO", "HAI:HOI"]
    args.git_commit = None
    args.git_folder = None
    args.settings_toml = None
    return args


def get_toml(tmp_path, defaultargs):
    return toml.load(tmp_path / defaultargs.project / ".template_settings.toml")

"""
These are tests of private functions, and not the API.
They may break even if the functionality is intact. If
so, it is OK to delete the breaking tests.
"""

def test_git_folder_does_not_exist():
    assert not Path("tests/data/git_template/.git").exists(), "If this test fails, something is wrong with the repository, not the code. The .git folder should not exist within tests/data/git_template."

def test_find_patterns_in_file_names():
    files = ["hei", "ja%var1%", "h%var2%q%var3%", "ja", "hei%var2%"]
    vars = project_from_template._find_vars_in_file_names(files)
    assert "var1" in vars
    assert "var2" in vars 
    assert  "var3" in vars
    assert len(vars) == 3

def test_find_patterns_in_files():
    filename = "tests/data/my_template/jau.txt"
    vars = project_from_template._find_vars_in_file(filename)
    assert "var1" in vars
    assert "var3" in vars
    assert "var4" in vars
    assert len(vars) == 3

def test_find_all_vars():
    folder = "tests/data/my_template"
    vars = project_from_template._find_required_vars(project_from_template._list_of_files(Path(folder)))
    assert "var1" in vars
    assert "var2" in vars
    assert "var3" in vars
    assert "var4" in vars
    assert "var5" in vars
    assert "var6" in vars
    assert len(vars) == 6

def test_add_free_args():
    args = argparse.Namespace()
    args.var0 = "v"
    args.variables = ["var1:KADÅ", "var2:hei"]
    project_from_template._add_free_vars_to_args(args)
    assert args.var0 == "v"
    assert args.var1 == "KADÅ"
    assert args.var2 == "hei"
    assert not hasattr(args, "variables")

def test_raise_exception_if_not_variable_present():
    args = argparse.Namespace()
    args.var0 = "v"
    vars = {"var0"}
    #no exception here
    project_from_template._exception_if_required_args_are_not_present(args, vars)
    #exception here
    vars = {"var0", "var1"}
    with pytest.raises(Exception, match=".*var1.*"):
        project_from_template._exception_if_required_args_are_not_present(args, vars)

def test_replace_file_names(tmp_path):
    args = argparse.Namespace()
    args.var4 = "foo"
    args.var5 = "bar"
    args.hei = "irrelevant"
    
    project_from_template._replace_filenames(["tests/data/my_template/%var4%-%var5%^%hei%.txt"], args, tmp_path, "tests/data")

    assert (tmp_path / "my_template/foo-bar%hei%.txt").exists()

def test_escape_file_names(tmp_path):
    args = argparse.Namespace()
    args.var4 = "foo"
    args.var5 = "bar"
    
    project_from_template._replace_filenames(["tests/data/my_template/^%var4^%%var5%.txt"], args, tmp_path, "tests")

    assert (tmp_path / "data/my_template/%var4%bar.txt").exists()

def test_replace_file_content(tmp_path):
    args = argparse.Namespace()
    args.var1 = "world"
    args.var2 = "!"
    tmp_path.mkdir(parents=True, exist_ok=True)
    file = tmp_path / "my_file.txt"
    file.write_text("Hello %var1%%var2%")

    project_from_template._replace_file_contents(file, args)

    assert file.read_text() == "Hello world!"

def test_clone_repo(tmp_path, git_test_repo_path):
    args = argparse.Namespace()
    args.git_repo = git_test_repo_path
    #args.git_commit = "4d94fac5"
    args.git_commit = None
    args.git_folder = None

    template_path = project_from_template._clone_and_check_out(args, tmp_path)

    assert (tmp_path / r"%project%-file.txt").exists()

def test_clone_repo_specific_commit(tmp_path, git_test_repo_path):
    args = argparse.Namespace()
    args.git_repo = git_test_repo_path
    args.git_commit = "ae481533"
    args.git_folder = None

    template_path = project_from_template._clone_and_check_out(args, tmp_path)

    assert (tmp_path / ".gitignore").exists()
    assert not (tmp_path / r"%project%-file.txt").exists()

def test_exception_when_no_repo(tmp_path):
    args = argparse.Namespace()
    args.git_repo = Path("no/repo/here")
    args.git_commit = None
    args.git_folder = None

    with pytest.raises(project_from_template.TemplateError, match=".*clone git repo.*"):    
        project_from_template._clone_and_check_out(args, tmp_path)

def test_exception_when_wrong_commit_hash(tmp_path, git_test_repo_path):
    args = argparse.Namespace()
    args.git_repo = git_test_repo_path
    args.git_commit = "52655646"
    args.git_folder = None

    with pytest.raises(project_from_template.TemplateError, match=".*check out commit.*"):    
        project_from_template._clone_and_check_out(args, tmp_path)

"""
These are tests of the API, and should only be changed if the
functionality is changed
"""

def test_new_project_contains_toml_file(tmp_path, defaultargs, another_template_path):
    
    defaultargs.template = str(another_template_path)

    project_from_template.main(defaultargs)

    assert (tmp_path / defaultargs.project).exists()
    
    assert (tmp_path / defaultargs.project / ".template_settings.toml").exists()

    tomlfile = toml.load(tmp_path / defaultargs.project / ".template_settings.toml")
    
    assert tomlfile["project"] == "MyTestProject"
    assert tomlfile["description"] == defaultargs.description
    assert tomlfile["author"] == defaultargs.author
    assert tomlfile["email"] == defaultargs.email
    assert tomlfile["HEI"] == "HO"
    assert tomlfile["HAI"] == "HOI"
    assert not "variables" in tomlfile
    assert tomlfile["template"] == defaultargs.template_path.absolute().as_posix()


def test_new_project_created_from_git_repo(tmp_path, defaultargs, git_test_repo_path):
    
    defaultargs.template = git_test_repo_path

    project_from_template.main(defaultargs)

    assert (tmp_path / defaultargs.project).exists()
    
    assert (tmp_path / defaultargs.project / ".template_settings.toml").exists()

    tomlfile = toml.load(tmp_path / defaultargs.project / ".template_settings.toml")
    
    assert tomlfile["project"] == "MyTestProject"
    assert tomlfile["description"] == defaultargs.description
    assert tomlfile["author"] == defaultargs.author
    assert tomlfile["email"] == defaultargs.email
    assert tomlfile["HEI"] == "HO"
    assert tomlfile["HAI"] == "HOI"
    assert tomlfile["template"] == str(Path(defaultargs.template).absolute().as_posix()) #Should recognize that this is a local relative path and convert it to absolute
    assert tomlfile["git_commit"] == "2d59c9c"


def test_project_settings_in_toml_file(tmp_path, git_test_repo_direct_path):
    args = argparse.Namespace()
    args.settings_toml = "tests/data/.template_settings.toml"
    args.variables = None
    args.output_path = tmp_path
    
    project_from_template.main(args)


def test_finds_commit_if_local_source_is_repo(defaultargs, tmp_path, git_test_repo_path):
    defaultargs.template = git_test_repo_path

    project_from_template.main(defaultargs)

    tomlfile = toml.load(tmp_path / defaultargs.project / ".template_settings.toml")
    assert tomlfile["template"] == str(Path(git_test_repo_path).absolute().as_posix())
    assert tomlfile["git_commit"] == "2d59c9c"

@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Depends on remote repo.")
def test_remote_repo(defaultargs, tmp_path):
    defaultargs.template = "http://devtools/info-group/gitlab-wiki.git"

    project_from_template.main(defaultargs)

def test_ignores_that_local_source_is_repo_and_emits_warning_if_files_changed(defaultargs, git_test_repo_path, tmp_path, capsys):    
    defaultargs.template = git_test_repo_path
    #create new file so repo is not pristine
    (Path(git_test_repo_path) / "newfile.txt").touch()

    project_from_template.main(defaultargs)

    tomlfile = toml.load(tmp_path / defaultargs.project / ".template_settings.toml")

    assert tomlfile["template"] == Path(git_test_repo_path).absolute().as_posix()
    assert capsys.readouterr().out.startswith("Warning: ")


def test_use_origin_if_exists_and_has_commit(defaultargs, tmp_path, tmp_path_factory, git_test_repo_path):
    
    newpath = tmp_path_factory.mktemp("local")
    subprocess.run(['git', 'clone', git_test_repo_path, newpath])
    #Origin of repo in newpath should be in git_test_repo_path

    defaultargs.template = str(newpath)

    project_from_template.main(defaultargs)

    tomlfile = toml.load(tmp_path / defaultargs.project / ".template_settings.toml")

    assert tomlfile["template"] == git_test_repo_path

def test_dont_use_origin_if_doesnt_have_commit(defaultargs, tmp_path, tmp_path_factory, git_test_repo_path):
    newpath = tmp_path_factory.mktemp("local")
    subprocess.run(['git', 'clone', git_test_repo_path, newpath])
    #Origin of repo in newpath should be in git_test_repo_path
    
    #Make new commit in local repo that doesn't exist in origin
    (newpath / "myfile.txt").touch()
    subprocess.run(['git', '-C', newpath, 'add', 'myfile.txt'])
    subprocess.run(['git', '-C', newpath, 'commit', '-m', 'Hei'])

    defaultargs.template = str(newpath)

    project_from_template.main(defaultargs)

    tomlfile = toml.load(tmp_path / defaultargs.project / ".template_settings.toml")

    assert tomlfile["template"] == Path(newpath).as_posix()

def test_git_folder_is_not_copied_to_new_project(defaultargs, tmp_path, git_test_repo_path):
    defaultargs.template = git_test_repo_path

    project_from_template.main(defaultargs)

    assert not (tmp_path / defaultargs.project / ".git").exists()
    


@pytest.mark.skip(reason="This test only works if there are no local changes, and the\
                  current repo is in sync with origin, and assumes that origin\
                  is devtools/python/template_generator")
def test_remote_url_is_correct_when_read_from_local_repo(defaultargs, tmp_path):
    defaultargs.templateh = Path("tests/data/another_template")

    project_from_template.main(defaultargs)

    tomlfile = get_toml(tmp_path, defaultargs)

    assert tomlfile["git_repo"] == "http://devtools/python/template-generator.git"
