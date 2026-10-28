
import subprocess
import os
from pathlib import Path


class GitError(Exception):
    pass


class DirtyRepositoryError(GitError):
    pass


def raise_giterror(error, result):
    output = result.stderr if result.stderr != "" else result.stdout
    raise GitError(f'{error}\nGit output:\n{output}')

def check_out(local_repo, item):
    """
    Check out the commit, branch or tag with name given in "item"
    """
    #result = subprocess.run(['git', '-C', local_repo, 'checkout', item, '--detach'], capture_output=True, text=True)            
    result = subprocess.run(['git', '-C', local_repo, 'checkout', item], capture_output=True, text=True)
    if result.returncode != 0:
        raise_giterror(f'Could not check out "{item}".', result)

def clone(repo, newdir, *args):
    clone_args = ['git', 'clone', repo, newdir]
    clone_args.extend(args)
    result = subprocess.run(clone_args, capture_output=True, text=True)
    if result.returncode != 0:
        raise_giterror('Could not clone git repo "{repo}".', result)

def is_branch(local_repo, item):
    result = subprocess.run(['git', '-C', local_repo, 'rev-parse', '--verify', f"refs/heads/{item}"], capture_output=True)
    return result.returncode == 0

def get_current_commit_hash(local_repo):
    result = subprocess.run(['git', '-C', local_repo,  'rev-parse', '--short', 'HEAD'], capture_output=True)
    if result.returncode == 0:
        return result.stdout.decode()[0:7]
    return ''

def has_local_changes(local_repo):
    result = subprocess.run(['git', '-C', local_repo, 'status', '--porcelain'], capture_output=True)
    if result.returncode == 0 and result.stdout == b'':
        return False
    return True

def get_origin(local_repo):
    result = subprocess.run(['git', '-C', local_repo, 'remote', 'get-url', 'origin'], capture_output=True)
    if result.returncode == 0 and result.stdout != b'':
        return result.stdout.decode()[0:-1]
    return None

def hash_exists_on_origin(local_repo, hash):
    subprocess.run(['git', '-C', local_repo, 'fetch'])
    result = subprocess.run(['git', '-C', local_repo, 'branch', '-r', '--contains', hash], capture_output=True)
    if result.returncode != 0 or result.stdout == b'':
        return False
    return True

def dir_contains_repo(local_repo):
    result = subprocess.run(['git', '-C', local_repo, 'rev-parse'])
    return result.returncode == 0


def is_work_tree(local_repo):
    result = subprocess.run(
        ['git', '-C', local_repo, 'rev-parse', '--is-inside-work-tree'],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == 'true'


def tracked_files(local_repo):
    """Return tracked paths relative to this directory, without walking untracked trees."""
    result = subprocess.run(
        ['git', '-C', local_repo, 'ls-files', '-z', '--cached', '--recurse-submodules'],
        capture_output=True,
    )
    if result.returncode != 0:
        raise GitError(f'Could not list tracked files in {local_repo}: '
                       f'{os.fsdecode(result.stderr)}')
    return {Path(os.fsdecode(name)) for name in result.stdout.split(b'\0') if name}


def require_clean(local_repo):
    result = subprocess.run(
        ['git', '-C', local_repo, 'status', '--porcelain', '--untracked-files=all'],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise_giterror(f'Could not check repository status in {local_repo}.', result)
    if result.stdout:
        raise DirtyRepositoryError(
            f'Repository in {local_repo} has uncommitted changes '
            '(including untracked files). Commit or stash them before updating.'
        )


def restore_work_tree(local_repo):
    # Limit restoration to the updated folder, including when it is a subfolder.
    result = subprocess.run(
        ['git', '-C', local_repo, 'restore', '--source=HEAD', '--worktree', '--', '.'],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise_giterror(f'Could not restore files in {local_repo} from Git.', result)

def init(dir):
    result = subprocess.run(['git', '-C', dir, 'init', '--initial-branch=main'], capture_output=True, text=True)
    if result.returncode != 0:
        raise_giterror('Could not initialize git repository.', result)

def branch(local_repo, newbranch):
    result = subprocess.run(['git', '-C', local_repo, 'branch', newbranch], capture_output=True, text=True)
    if result.returncode != 0:        
        raise_giterror('Could not branch repo "{local_repo}".', result)

def merge(local_repo, merge_from):
    """
    Returns a list of conflicted files
    """
    result = subprocess.run(['git', '-C', local_repo, 'merge', merge_from], capture_output=True, text=True)    
    if result.returncode == 0:
        return []
    elif result.returncode == 1:
        conflicts = get_conflicted_files(local_repo)
        if conflicts:
            return conflicts
        raise_giterror(f'Could not merge repo {local_repo}', result)
    else:
        raise_giterror(f'Could not merge repo {local_repo}', result)

def checkout(local_repo, branch):
    result = subprocess.run(['git', '-C', local_repo, 'checkout', branch], capture_output=True, text=True)
    if result.returncode != 0:        
        raise_giterror(f'Could not check out from repo {local_repo}.', result)

def commit(local_repo, message, *, allow_empty=False):
    command = ['git', '-C', local_repo, 'commit', '-m', message]
    if allow_empty:
        command.append('--allow-empty')
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise_giterror(f'Could not commit to repo {local_repo}.', result)

def add_all(local_repo):
    result = subprocess.run(['git', '-C', local_repo, 'add', '--all'], capture_output=True, text=True)
    if result.returncode != 0:
        raise_giterror(f'Could not add all to repo {local_repo}.', result)
    
def get_conflicted_files(local_repo):
    command = ['git', '-C', local_repo, 'diff', '--name-only', '--diff-filter=U']
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise_giterror(f'Could not list merge conflicts in {local_repo}.', result)
    return result.stdout.splitlines()

def push(local_repo, remote = None):
    command = ['git', '-C', local_repo, 'push']
    if remote is not None:
        subprocess.run(['git', '-C', local_repo, 'remote', 'add', 'origin', remote], capture_output=True, text=True)
        command.extend(['--set-upstream', 'origin', 'main'])
    result = subprocess.run(command)
    if result.returncode != 0:
        raise_giterror(f'Could not push repo {local_repo} to {remote}.', result)
