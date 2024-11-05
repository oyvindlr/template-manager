from template_generator import git_wrapper as git
import argparse
import os
import toml
import sys
import requests
from pathlib import Path

def parse_args(argv):
    parser = argparse.ArgumentParser(description="Create a new GitLab project.")

    # Optional arguments
    parser.add_argument("-g", "--group", type=str, help="The group in GitLab to place the project under.")
    parser.add_argument("-p", "--path", type=str, help="Path to the folder where the project is currently located.", default = ".")
    parser.add_argument("-t", "--token", type=str, help="Your GitLab access token.")
    parser.add_argument("-v", "--visibility", type=str, choices=["private", "internal", "public"],
                        help="The visibility level of the project (private, internal, public).", default="public")
    parser.add_argument("-s", "--gitlab-server", type=str,
                        help="Gitlab server URL", default="http://devtools")
    parser.add_argument("-r", "--print-groups", action="store_true",
                        help="Print available groups and exit.")

    args = parser.parse_args(argv)
    return args

def _get_group_id(args, headers):
    search_url = f"{args.gitlab_server}/api/v4/groups?search={args.group}"
    try:
        response = requests.get(search_url, headers=headers)
    except requests.exceptions.RequestException as ex:
        print(f"Failed to connect to {search_url} :", ex)
        exit(1)
    if response.status_code != 200:
        print("Failed get group id:", response.text)
        exit(1)
    groups = response.json()
    if not groups:
        print(f'Group "{args.group}" not found')
        exit(1)
    return groups[0]['id']

def _get_available_groups(args, headers):
    search_url = f"{args.gitlab_server}/api/v4/groups"
    try:
        response = requests.get(search_url, headers=headers)
    except requests.exceptions.RequestException as ex:
        print(f"Failed to connect to {search_url} :", ex)
        exit(1)
    if response.status_code != 200:
        print("Failed get available groups:", response.text)
        exit(1)
    resp = response.json()
    groups = [group["name"] for group in resp]
    return groups

def _create_project(args):
    headers = {"PRIVATE-TOKEN":args.token}
    create_project_url = f"{args.gitlab_server}/api/v4/projects"
    json_content = {"name":args.name, "description":args.description, "visibility":args.visibility}
    if args.group is not None:
        group_id = _get_group_id(args, headers)
        json_content['namespace_id'] = group_id
    try:
        response = requests.post(create_project_url, headers=headers, json = json_content)  
    except requests.exceptions.RequestException as ex:
        print(f"Failed to connect to {create_project_url} :", ex)
        exit(1)
    if response.status_code == 201 or response.status_code == 200:
        print("Project created successfully")
    else:
        print("Failed to create project: ", response.text)
        exit(1)

def _push_code_to_new_project_repo(args):
    git.init(args.path)
    git.add_all(args.path)
    git.commit(args.path, "Initial commit")
    remote_repo = f"{args.gitlab_server}/{args.group}/{args.slug}.git"
    git.push(args.path, remote_repo)
    print("Project files successfully pushed to new project repository")


def _get_token(args):
    if not hasattr(args, "token") or args.token is None:
        args.token = os.getenv("GITLAB_TOKEN")
        if args.token is None:
            args.token = input(f"Please input your gitlab API token\nTo obtain a new token, visit {args.gitlab_server}/-/user_settings/personal_access_tokens\n(To avoid this step in the future, store your token in an environment variable with the key \"GITLAB_TOKEN\")\n")
            if args.token == "":
                print("No token given. Exiting.")
                exit(0)

def print_available_grups(args):    
    _get_token(args)
    groups = _get_available_groups(args, {"PRIVATE-TOKEN":args.token})
    print("\n".join(groups))

def _main(args):
    """
    Handles the main logic of the program, including:
    - Checking for a valid path to a folder
    - Checking for a valid .template_settings.toml file in the given path
    - Getting the name and description of the project from the .template_settings.toml file, or from user input if no such file exists
    - Calling the _create_project function with the given arguments

    :param args: the arguments given to the program
    :type args: argparse.Namespace
    """    
    _get_token(args)

    if args.print_groups:
        print_available_grups(args)
        exit(0)
    
    project_path = Path(args.path)
    if not project_path.exists():
        print("Path not found: "+ args.path)
        exit(1)
    toml_path = project_path / ".template_settings.toml"
    if not toml_path.exists():
        print("No \".template_settings.toml\" file found in current/given path. You will need to manually enter a name and description of the project.")
        fname = project_path.absolute().name
        args.name = input(f"Project name: (hit enter to use \"{fname}\"): ")
        if args.name == "":
            args.name = fname
        args.description = input("Project description: ")
    else:
        tomlfile = toml.load(toml_path)
        args.name = tomlfile["project"]
        args.description = tomlfile["description"]
    args.slug = args.name.replace(" ", "-").lower()
    
    _create_project(args)
    _push_code_to_new_project_repo(args)

def main(argv):
    args = parse_args(argv)
    _main(args)

def entry_point():
    main(sys.argv[1:])

if __name__ == "__main__":
    entry_point()
        

    
            
            
            