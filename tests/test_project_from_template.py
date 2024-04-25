import pytest
import argparse
from template_generator import project_from_template
from pathlib import Path

"""
These are tests of private functions, and not the API.
They may break even if the functionality is intact. If
so, it is OK to delete the breaking tests.
"""

def test_find_patterns_in_file_names():
    files = ["hei", "ja%var1%", "h%var2%q%var3%", "ja", "hei%var2%"]
    vars = project_from_template._find_vars_in_file_names(files)
    assert "var1" in vars
    assert "var2" in vars 
    assert  "var3" in vars
    assert len(vars) == 3

def test_find_patterns_in_files():
    filename = "tests/data/jau.txt"
    vars = project_from_template._find_vars_in_file(filename)
    assert "var1" in vars
    assert "var3" in vars
    assert "var4" in vars
    assert len(vars) == 3

def test_find_all_vars():
    folder = "tests/data"
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
    freevars = ["var1:KADÅ", "var2:hei"]
    project_from_template._add_free_vars_to_args(freevars, args)
    assert args.var0 == "v"
    assert args.var1 == "KADÅ"
    assert args.var2 == "hei"

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
    
    project_from_template._replace_filenames(["tests/data/%var4%-%var5%_%hei%.txt"], args, tmp_path, "tests")

    assert (tmp_path / "data/foo-bar_%hei%.txt").exists()

def test_escape_file_names(tmp_path):
    args = argparse.Namespace()
    args.var4 = "foo"
    args.var5 = "bar"
    
    project_from_template._replace_filenames(["tests/data/_%var4%_%var5%_.txt"], args, tmp_path, "tests")

    assert (tmp_path / "data/_%var4%_%var5%_.txt").exists()

def test_replace_file_content(tmp_path):
    args = argparse.Namespace()
    args.var1 = "world"
    args.var2 = "!"
    tmp_path.mkdir(parents=True, exist_ok=True)
    file = tmp_path / "my_file.txt"
    file.write_text("Hello %var1%%var2%")

    project_from_template._replace_file_contents(file, args)

    assert file.read_text() == "Hello world!"




