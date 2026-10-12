import pytest
import pytest_mock
import argparse
from template_manager import create_gitlab_project

@pytest.fixture
def default_args():
    args = argparse.Namespace()
    args.group = "group"
    args.gitlab_server = "http://devtools"
    return args

@pytest.fixture
def actual_headers():
    return {"PRIVATE-TOKEN": "enter_token_here_to_run_test"}


def test_find_group_id(requests_mock, default_args):
    headers = {"RAI": "JAU"}
    requests_mock.get("http://devtools/api/v4/groups?search=group", json=[{"id": 1}], headers=headers, status_code=200)
    
    assert create_gitlab_project._get_group_id(default_args, headers) == 1
    

@pytest.mark.skip(reason="Requires access to gitlab")
def test_actual_get_group_id(default_args, actual_headers):
    default_args.group = "python"
    
    assert create_gitlab_project._get_group_id(default_args, actual_headers) == 13

@pytest.mark.skip(reason="Requires access to gitlab")
def test_actual_get_nonexistent_group_id(default_args, actual_headers, capsys):
    default_args.group = "nonexistent-group"    
    with pytest.raises(SystemExit):
        create_gitlab_project._get_group_id(default_args, actual_headers)
    assert capsys.readouterr().out == "Group \"nonexistent-group\" not found\n"

@pytest.mark.skip(reason="Depends on data on currently on gitlab")
def test_actual_get_available_groups(default_args, actual_headers):
        
    available = create_gitlab_project._get_available_groups(default_args, actual_headers)
    assert "python" in available

@pytest.mark.skip(reason="Depends on data on currently on gitlab")
def test_actual_print_groups(default_args, actual_headers, capsys):
    default_args.print_groups = True
    default_args.token = actual_headers["PRIVATE-TOKEN"]
    
    with pytest.raises(SystemExit):
        create_gitlab_project._main(default_args)

    assert capsys.readouterr().out == "Data analysis\ndevops\ngeneral\nInfo group\npython\n"

@pytest.mark.skip(reason="Actually pushes code to gitlab, which we cannot do regularly.")
def test_push_project(default_args, capsys):
    default_args.name = "mytestproject"
    default_args.path = "tests/data/tobepushed"
    default_args.group = "oyro"

    create_gitlab_project._push_code_to_new_project_repo(default_args)

    assert capsys.readouterr().out == "Project files successfully pushed to new project repository\n"

@pytest.mark.skip(reason="Actually creates a project, which we cannot do regularly.")
def test_create_actual_project(default_args, actual_headers, capsys):
    default_args.name = "mytestproject"
    default_args.group = None
    default_args.description = "My test project"
    default_args.visibility = "private"
    default_args.path = "anypath"
    default_args.token = actual_headers["PRIVATE-TOKEN"]

    create_gitlab_project._create_project(default_args)

    assert capsys.readouterr().out == "Project created successfully\n"


"""
def test_create_project_looks_for_token():
    args = argparse.Namespace()
    create_gitlab_project._main(args)
"""