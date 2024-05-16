
import subprocess


class GitError(Exception):
    pass

def check_out_commit(local_repo, commit):
    result = subprocess.run(['git', '-C', local_repo, 'checkout', commit, '--detach'], capture_output=True)            
    if result.returncode != 0:
        raise GitError(f'Could not check out commit "{commit}".\nGit output:\n{result.stderr.decode()}')

def clone(repo, newdir, *args):
    clone_args = ['git', 'clone', repo, newdir]
    clone_args.extend(args)
    result = subprocess.run(clone_args, capture_output=True)
    if result.returncode != 0:
        raise GitError(f'Could not clone git repo "{repo}".\nGit output:\n{result.stderr.decode()}')

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

def init(dir):
    result = subprocess.run(['git', '-C', dir, 'init'])
    if result.returncode != 0:
        raise GitError(f'Could not initialize git repository.\nGit output:\n{result.stderr.decode()}')

def branch(local_repo, newbranch):
    result = subprocess.run(['git', '-C', local_repo, 'branch', newbranch])
    if result.returncode != 0:
        raise GitError(f'Could not branch repo {local_repo}.\nGit output:\n{result.stderr.decode()}')

def merge(local_repo, merge_from):
    """
    Returns a list of conflicted files
    """
    result = subprocess.run(['git', '-C', local_repo, 'merge', merge_from], capture_output=True, text=True)    
    if result.returncode == 0:
        return []
    elif result.returncode == 1: #Conflicts
        return get_conflicted_files(local_repo)
    else:
        raise GitError(f'Could not merge repo {local_repo}.\nGit output:\n{result.stderr}')

def checkout(local_repo, branch):
    result = subprocess.run(['git', '-C', local_repo, 'checkout', branch])
    if result.returncode != 0:
        raise GitError(f'Could not check out from repo {local_repo}.\nGit output:\n{result.stderr.decode()}')

def commit(local_repo, message):
    result = subprocess.run(['git', '-C', local_repo, 'commit', '-m', message])
    if result.returncode != 0:
        raise GitError(f'Could not commit to repo {local_repo}.\nGit output:\n{result.stderr.decode()}')

def add_all(local_repo):
    result = subprocess.run(['git', '-C', local_repo, 'add', '--all'])
    if result.returncode != 0:
        raise GitError(f'Could not add all to repo {local_repo}.\nGit output:\n{result.stderr.decode()}')
    
def get_conflicted_files(local_repo):
    command = ['git', '-C', local_repo, 'diff', '--name-only', '--diff-filter=U']
    result = subprocess.run(command, stdout=subprocess.PIPE, text=True)
    conflicted_files = result.stdout.strip().split('\n')
    return conflicted_files