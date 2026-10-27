"""Isolated, resumable reverse-sync orchestration. Artifacts stay outside source trees."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

import toml
from platformdirs import user_cache_dir

from . import __version__
from . import project_from_template as generator
from . import reverse_sync as sync

MANIFEST = '.template_render_manifest.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    temporary.replace(path)


def contained(root, relative):
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise sync.ReverseSyncError(f'Path escapes workspace source: {relative}')
    return path


def source_location(repo, source):
    for candidate in (repo / source, repo.parent / source):
        if candidate.exists():
            return str(candidate.resolve())
    return source


def clone(source, destination):
    result = subprocess.run(['git', 'clone', '--no-checkout', '--', str(source), str(destination)],
                            capture_output=True, text=True)
    if result.returncode:
        raise sync.ReverseSyncError(result.stderr.strip())


def snapshot(cache, revision, destination, branch=None):
    clone(cache, destination)
    args = ('checkout', '-b', branch, revision) if branch else ('checkout', '--detach', revision)
    sync._git(destination, *args)


def tree_hash(source):
    digest = hashlib.sha256()
    for name in sorted(generator._list_of_files(source)):
        path = Path(name)
        if path.is_symlink():
            raise sync.ReverseSyncError(f'Symlinks require manual review: {path}')
        digest.update(json.dumps([path.relative_to(source).as_posix(), path.stat().st_mode,
                                  hashlib.sha256(path.read_bytes()).hexdigest()]).encode())
    return digest.hexdigest()


def render(source, settings, destination, cache):
    """Use the actual source snapshot, never clone the revision in saved settings."""
    settings = dict(settings)
    settings.setdefault('uuid_seed', 'reverse-sync-legacy-paths')
    settings.setdefault('date', '1970-01-01')
    key = hashlib.sha256(json.dumps([__version__, tree_hash(source), settings],
                                    sort_keys=True).encode()).hexdigest()
    cached = cache / 'renders' / key
    if cached.exists():
        shutil.copytree(cached, destination)
        return read(destination / MANIFEST)
    args = argparse.Namespace(**{**settings, 'settings_toml': None, 'variables': None,
                                'output_path': destination, 'no_gitlab_project': True})
    generator._build(args, render_date=settings['date'], template_path=source)
    cached.parent.mkdir(parents=True, exist_ok=True)
    if not cached.exists():
        shutil.copytree(destination, cached)
    return read(destination / MANIFEST)


def load(workspace):
    workspace = Path(workspace).resolve()
    return workspace, read(workspace / 'workspace.json')


def prepare(repo, workspace, since=None, until='HEAD', remote='origin', template_base='main',
            checkpoint_ref=sync.DEFAULT_REF, cache=None, alternate_settings=None,
            includes=(), excludes=()):
    repo = Path(sync._git(repo, 'rev-parse', '--show-toplevel').decode().strip())
    workspace = Path(workspace).resolve()
    until = sync._commit(repo, until)
    settings = toml.loads(sync._settings(repo, until))
    source = source_location(repo, settings['template'])
    publication_source = source
    if Path(source).exists():
        result = subprocess.run(['git', '-C', source, 'remote', 'get-url', 'origin'],
                                capture_output=True, text=True)
        if result.returncode == 0:
            publication_source = result.stdout.strip()
    for tree in (repo, Path(source)):
        if tree.exists() and workspace.is_relative_to(tree.resolve()):
            raise sync.ReverseSyncError('Workspace must be outside the project and template repositories.')
    workspace.mkdir(parents=True, exist_ok=False)
    cache = Path(cache or user_cache_dir('template-manager')).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    # Cache the saved source for pinned historical objects. A local source clone may
    # have unpublished or stale branches, so it must not supply the proposal base.
    repository = cache / ('repo-' + hashlib.sha256(source.encode()).hexdigest())
    if not repository.exists():
        clone(source, repository)
    sync._git(repository, 'fetch', 'origin', '+refs/heads/*:refs/remotes/origin/*', '--tags')
    publication_repository = repository
    if publication_source != source:
        publication_repository = cache / ('repo-' + hashlib.sha256(publication_source.encode()).hexdigest())
        if not publication_repository.exists():
            clone(publication_source, publication_repository)
        sync._git(publication_repository, 'fetch', 'origin',
                  '+refs/heads/*:refs/remotes/origin/*', '--tags')
    base = sync._commit(publication_repository,
                        template_base if re.fullmatch(r'[0-9a-f]{40}', template_base)
                        else f'refs/remotes/origin/{template_base}')
    pinned = sync._commit(repository, settings['git_commit'])
    patch, all_patch, report = sync.review(repo, until, checkpoint_ref, since,
                                         includes=includes, excludes=excludes,
                                         remote=remote or None, template_base=template_base)
    remote_state = report['checkpoint']['remote']
    if remote_state['status'] == 'error':
        raise sync.ReverseSyncError(remote_state['error'])
    if remote_state['sha'] and remote_state['sha'] != report['checkpoint']['local']:
        raise sync.ReverseSyncError('Local and remote checkpoints differ; reconcile before preparing.')
    (workspace / 'changes.diff').write_bytes(patch)
    (workspace / 'all-changes.diff').write_bytes(all_patch)
    write(workspace / 'review.json', report)
    (workspace / 'review.md').write_text(sync._review_markdown(report), encoding='utf-8', errors='backslashreplace')
    branch = 'reverse-sync/' + report['until'][:12]
    snapshot(publication_repository, base, workspace / 'template', branch)
    snapshot(publication_repository, base, workspace / 'base')
    snapshot(repository, pinned, workspace / 'original')
    settings = {**settings, 'date': settings.get('date', '1970-01-01'),
                'uuid_seed': settings.get('uuid_seed', 'reverse-sync-legacy-paths')}
    alternate = {**settings, 'project': 'Reverse Sync Alternate'}
    if alternate_settings:
        alternate.update(toml.load(alternate_settings))
    # Location/revision/seed are controlled by the workspace for both fixtures.
    for key in ('template', 'git_commit', 'git_folder', 'uuid_seed', 'date'):
        if key in settings:
            alternate[key] = settings[key]
    for label, values in (('source', settings), ('alternate', alternate)):
        (workspace / f'{label}-settings.toml').write_text(toml.dumps(values), encoding='utf-8')
    folder = settings.get('git_folder') or '.'
    original_manifest = render(contained(workspace / 'original', folder), settings,
                               workspace / 'original-render', cache)
    current_manifest = render(contained(workspace / 'base', folder), settings,
                              workspace / 'base-render', cache)
    mapping = {}
    for item in original_manifest['files']:
        mapping.setdefault(item['rendered_path'], []).append(item['template_path'])
    current = {f['rendered_path']: f for f in current_manifest['files']}
    decisions = []
    for index, entry in enumerate(report['files']):
        path = entry['paths'][-1]
        candidates = mapping.get(path, [])
        disposition = 'requires-review'
        if (entry['status'] == 'M' and len(candidates) == 1 and path in current
                and sync._git(repo, 'show', f"{report['until']}:{path}") ==
                (workspace / 'base-render' / path).read_bytes()):
            disposition = 'already upstream'
        decisions.append({'id': index, 'paths': entry['paths'], 'status': entry['status'],
                          'hint': entry['classification_hint'], 'included': entry['included'],
                          'template_paths': candidates, 'disposition': disposition,
                          'reason': '', 'application': 'pending'})
    write(workspace / 'decisions.json', {'schema_version': 1, 'groups': decisions})
    state = {'schema_version': 1, 'project': str(repo), 'since': report['since'],
             'until': report['until'], 'checkpoint': report['checkpoint'],
             'template_base': base, 'template_base_name': template_base, 'pinned_template': pinned,
             'template_source': publication_source, 'folder': folder, 'branch': branch, 'cache': str(cache),
             'paths': {'template': str(workspace / 'template'), 'review': str(workspace / 'review.json')},
             'commands': {name: ['template-reverse-sync', name, '--workspace', str(workspace)]
                          for name in ('apply', 'validate', 'publish')}, 'publication': None}
    write(workspace / 'workspace.json', state)
    return state


def parameter_values(settings):
    args = argparse.Namespace(**settings)
    generator._add_special_variables(args)
    # Only real substitution names, never incidental generator configuration values.
    return vars(args)


def apply(workspace):
    """Apply accepted literal edits only. All parameter/conditional ambiguity stays manual."""
    workspace, state = load(workspace)
    decisions = read(workspace / 'decisions.json')
    settings = toml.load(workspace / 'source-settings.toml')
    values = parameter_values(settings)
    source_root = contained(workspace / 'template', state['folder'])
    original_root = contained(workspace / 'original', state['folder'])
    for group in decisions['groups']:
        if group['disposition'] != 'accepted' or group['application'] == 'applied':
            continue
        group['application'] = 'requires-review'
        if group['status'] != 'M' or len(group['template_paths']) != 1:
            group['reason'] = 'Automatic application supports uniquely mapped text modifications only.'
            continue
        path, template_path = group['paths'][-1], group['template_paths'][0]
        original = contained(original_root, template_path)
        target = contained(source_root, template_path)
        try:
            modes = [sync._git(state['project'], 'ls-tree', rev, '--', path).split()[0]
                     for rev in (state['since'], state['until'])]
            if modes[0] != modes[1]:
                raise ValueError('File mode changes require review.')
            source = original.read_bytes().decode('utf-8')
            old = contained(workspace / 'original-render', path).read_bytes().decode('utf-8')
            before = sync._git(state['project'], 'show', f"{state['since']}:{path}").decode('utf-8')
            after = sync._git(state['project'], 'show', f"{state['until']}:{path}").decode('utf-8')
            if before != old or not target.exists() or target.read_bytes() != original.read_bytes():
                raise ValueError('Project baseline or current template differs from pinned template.')
            if re.search(r'{%|%\s*(?:if\(|elseif\(|else%|endif%)', source):
                raise ValueError('Conditional template requires review.')
            # Map only identical lines; never inverse-render placeholders or expressions.
            src, rendered = source.splitlines(keepends=True), old.splitlines(keepends=True)
            line_map = {}
            for a, b, length in difflib.SequenceMatcher(None, src, rendered, autojunk=False).get_matching_blocks():
                line_map.update({b + n: a + n for n in range(length)})
            substitutions = re.findall(r'%([A-Za-z_]\w*)%|{{\s*(?:cookiecutter\.)?([A-Za-z_]\w*)\s*}}', source + '\n' + template_path)
            parameter_literals = [str(values[name]) for pair in substitutions for name in pair
                                  if name and name in values and str(values[name])]
            edits = []
            for tag, i, j, a, b in difflib.SequenceMatcher(None, rendered, after.splitlines(keepends=True), autojunk=False).get_opcodes():
                if tag == 'equal':
                    continue
                new = after.splitlines(keepends=True)[a:b]
                if re.search(r'{{|{%|%[A-Za-z_]\w*%', ''.join(new)):
                    raise ValueError('New template syntax requires review.')
                if any(value in ''.join(new) for value in parameter_literals):
                    raise ValueError('New lines contain parameter values; adapt placeholders manually.')
                if i == j:  # Insertions need unambiguous literal neighbors.
                    if i == 0 or i == len(rendered) or i - 1 not in line_map or i not in line_map or line_map[i] != line_map[i-1] + 1:
                        raise ValueError('Insertion touches a substitution or file boundary.')
                    if source.count(''.join(rendered[i-1:i+1])) != 1:
                        raise ValueError('Repeated insertion context requires review.')
                    start = end = line_map[i]
                else:
                    indices = [line_map.get(n) for n in range(i, j)]
                    if None in indices or indices != list(range(indices[0], indices[0] + len(indices))):
                        raise ValueError('Edit intersects a substitution or ambiguous span.')
                    literal = ''.join(rendered[i:j])
                    if source.count(literal) != 1 or old.count(literal) != 1:
                        raise ValueError('Repeated literal spans require review.')
                    start, end = indices[0], indices[-1] + 1
                edits.append((start, end, new))
            for start, end, new in reversed(edits):
                src[start:end] = new
            target.write_bytes(''.join(src).encode('utf-8'))
            group['application'] = 'applied'
            group['reason'] = 'Applied literal spans; placeholders preserved.'
        except (UnicodeError, OSError, ValueError) as exc:
            group['reason'] = str(exc)
    write(workspace / 'decisions.json', decisions)
    return decisions


def failure_kind(output):
    patterns = {'tls': r'certificate verify failed|SSL certificate problem|unable to get local issuer',
                'dns': r'could not resolve host|name or service not known|no such host is known',
                'authentication': r'authentication failed|401 unauthorized|403 forbidden|permission denied \(publickey\)',
                'timeout': r'timed out|timeout expired'}
    return next((kind for kind, pattern in patterns.items() if re.search(pattern, output, re.I)), None)


def run_test(command, output, source, timeout, log):
    started = time.monotonic()
    argv = [part.replace('{output}', str(output)).replace('{template}', str(source)) for part in command]
    try:
        result = subprocess.run(argv, cwd=output, capture_output=True, text=True, timeout=timeout)
        content = result.stdout + result.stderr
        code = result.returncode
    except subprocess.TimeoutExpired:
        content, code = 'Test timed out', 124
    except OSError as exc:
        content, code = str(exc), 127
    Path(log).write_text(content, encoding='utf-8')
    return {'command': argv, 'returncode': code, 'seconds': round(time.monotonic()-started, 3),
            'failure_kind': failure_kind(content) if code else None, 'log': str(log)}


def rendered_test_contract(output):
    path = Path(output) / '.template-tests.toml'
    if not path.exists():
        return None, 300
    contract = toml.load(path)
    command = contract.get('command')
    if (command is not None
            and (not isinstance(command, list) or not command
                 or not all(isinstance(value, str) for value in command))):
        raise ValueError('Rendered test command must be a nonempty argv array of strings.')
    return command, contract.get('timeout', 300)


def scan(output, source_values, alternate_values):
    findings = []
    leaked = set()
    for key, value in source_values.items():
        other = alternate_values.get(key)
        if other is not None and value != other and len(str(value)) >= 4:
            leaked.add(str(value))
    for name in generator._list_of_files(output):
        path = Path(name)
        if path.name in (MANIFEST, sync.SETTINGS):
            continue
        try:
            text = path.relative_to(output).as_posix() + '\n' + path.read_text(encoding='utf-8')
        except UnicodeError:
            text = path.relative_to(output).as_posix()
        if re.search(r'%[A-Za-z_]\w*%|{{\s*(?:cookiecutter\.)?\w+\s*}}|{%\s*(?:if|endif|else|for)\b', text):
            findings.append({'path': str(path.relative_to(output)), 'kind': 'unresolved-placeholder'})
        for value in sorted(leaked):
            if value in text:
                findings.append({'path': str(path.relative_to(output)), 'kind': 'source-value-leak', 'value': value})
    return findings


def validate(workspace, run_tests=False):
    workspace, state = load(workspace)
    settings = toml.load(workspace / 'source-settings.toml')
    alternate = toml.load(workspace / 'alternate-settings.toml')
    source = contained(workspace / 'template', state['folder'])
    base = contained(workspace / 'base', state['folder'])
    contract_path = source / '.template-tests.toml'
    contract = toml.load(contract_path) if contract_path.exists() else {}
    command = contract.get('command')
    if command is not None and (not isinstance(command, list) or not command or not all(isinstance(v, str) for v in command)):
        raise sync.ReverseSyncError('Test command must be an argv array of strings.')
    if command and not run_tests:
        raise sync.ReverseSyncError('Template declares executable tests. Review .template-tests.toml, then use --run-tests.')
    results = []
    for label, values in (('source', settings), ('alternate', alternate)):
        # Every test starts with fresh output, including on repeated validation.
        root = workspace / 'validation' / (label + '-' + str(time.time_ns()))
        root.mkdir(parents=True)
        output = root / 'patched'
        item = {'fixture': label, 'findings': [], 'classification': 'passed'}
        fixture_command = command
        try:
            render(source, values, output, Path(state['cache']))
            item['findings'] = scan(output, parameter_values(settings) if label == 'alternate' else {}, parameter_values(values))
            if command:
                fixture_command, fixture_timeout = rendered_test_contract(output)
                if fixture_command is None:
                    raise ValueError('Rendered test contract must declare a command.')
                item['test'] = run_test(fixture_command, output, source, fixture_timeout,
                                        root / 'patched.log')
            failed = bool(item['findings']) or item.get('test', {}).get('returncode', 0) != 0
        except (generator.TemplateError, OSError, ValueError) as exc:
            item['error'], failed = str(exc), True
        if failed:
            baseline = root / 'baseline'
            try:
                render(base, values, baseline, Path(state['cache']))
                baseline_findings = scan(baseline, parameter_values(settings) if label == 'alternate' else {}, parameter_values(values))
                item['baseline_findings'] = baseline_findings
                if command:
                    baseline_command, baseline_timeout = rendered_test_contract(baseline)
                    if baseline_command:
                        item['baseline_test'] = run_test(baseline_command, baseline, base,
                                                         baseline_timeout, root / 'baseline.log')
                test, baseline_test = item.get('test', {}), item.get('baseline_test', {})
                if (test.get('failure_kind') or baseline_test.get('failure_kind')
                        or test.get('returncode') == baseline_test.get('returncode') == 127):
                    item['classification'] = 'environment/network-failure'
                elif (not item.get('error') and item['findings'] == baseline_findings
                      and test.get('returncode', 0) == baseline_test.get('returncode', 0)
                      and (not command or (root / 'patched.log').read_bytes() == (root / 'baseline.log').read_bytes())):
                    item['classification'] = 'pre-existing-failure'
                else:
                    item['classification'] = 'regression'
            except (generator.TemplateError, OSError, ValueError) as exc:
                item['baseline_error'] = str(exc)
                item['classification'] = 'unresolved-failure'
        results.append(item)
    result = {'schema_version': 1, 'template_tree': tree_hash(source),
              'configuration_hash': hashlib.sha256(json.dumps([settings, alternate], sort_keys=True).encode()).hexdigest(),
              'test_status': 'executed' if command else 'not-declared', 'fixtures': results,
              'passed': all(item['classification'] == 'passed' for item in results)}
    write(workspace / 'validation.json', result)
    (workspace / 'validation.md').write_text('# Reverse-sync validation\n\n' +
        '\n'.join(f"- {item['fixture']}: {item['classification']}" for item in results) +
        f"\n- Template tests: {result['test_status']}\n", encoding='utf-8')
    return result


def resolved_decisions(workspace, report):
    groups = read(workspace / 'decisions.json')['groups']
    if [g['paths'] for g in groups] != [f['paths'] for f in report['files']]:
        raise sync.ReverseSyncError('Decisions must cover every review entry, in inventory order.')
    if any(g['disposition'] not in {'accepted', 'excluded', 'already upstream'} for g in groups):
        raise sync.ReverseSyncError('Unresolved or deferred dispositions remain in decisions.json.')
    return groups


def checked_run(argv, cwd):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise sync.ReverseSyncError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def publish(workspace, title='Promote reusable project improvements', draft=False, provider=None):
    workspace, state = load(workspace)
    report = read(workspace / 'review.json')
    groups = resolved_decisions(workspace, report)
    repo = workspace / 'template'
    source = contained(repo, state['folder'])
    validation = read(workspace / 'validation.json')
    configuration = [toml.load(workspace / name) for name in ('source-settings.toml', 'alternate-settings.toml')]
    configuration_hash = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    if validation['template_tree'] != tree_hash(source) or validation.get('configuration_hash') != configuration_hash:
        raise sync.ReverseSyncError('Template changed since validation. Run validate again.')
    if not validation['passed'] and not draft:
        raise sync.ReverseSyncError('Validation has failures; fix them or publish explicitly with --draft.')
    sync._git(repo, 'add', '--all')
    sync._git(repo, 'diff', '--check', state['template_base'])
    patch = sync._git(repo, 'diff', '--binary', state['template_base'])
    (workspace / 'template.patch').write_bytes(patch)
    if not patch:
        return {'status': 'no-changes'}
    check = workspace / ('patch-check-' + str(time.time_ns()))
    snapshot(repo, state['template_base'], check)
    checked_run(['git', 'apply', '--check', str(workspace / 'template.patch')], check)
    if sync._git(repo, 'diff', '--cached', '--name-only'):
        sync._git(repo, 'commit', '-m', title)
    proposal = sync._commit(repo, 'HEAD')
    sync._git(repo, 'remote', 'set-url', 'origin', state['template_source'])
    sync._git(repo, 'push', '--set-upstream', 'origin', state['branch'])
    body = (title + '\n\n' + (workspace / 'validation.md').read_text(encoding='utf-8') +
            '\nReview dispositions: ' + ', '.join(f"{kind}: {sum(g['disposition'] == kind for g in groups)}"
                                                 for kind in ('accepted', 'excluded', 'already upstream')) + '\n')
    body_file = workspace / 'proposal.md'
    body_file.write_text(body, encoding='utf-8')
    provider = provider or ('github' if 'github.com' in state['template_source'] else 'gitlab')
    if provider == 'github':
        existing = json.loads(checked_run(['gh', 'pr', 'list', '--head', state['branch'],
                              '--base', state['template_base_name'], '--state', 'open', '--json', 'url'], repo))
        if existing:
            url = existing[0]['url']
            checked_run(['gh', 'pr', 'edit', url, '--title', title, '--body-file', str(body_file)], repo)
            if draft:
                checked_run(['gh', 'pr', 'ready', url, '--undo'], repo)
        else:
            url = checked_run(['gh', 'pr', 'create', '--head', state['branch'], '--base', state['template_base_name'],
                               '--title', title, '--body-file', str(body_file)] + (['--draft'] if draft else []), repo)
    else:
        existing = json.loads(checked_run(['glab', 'mr', 'list', '--source-branch', state['branch'],
                                          '--target-branch', state['template_base_name'], '--output', 'json'], repo))
        if existing:
            url = existing[0]['web_url']
            checked_run(['glab', 'mr', 'update', str(existing[0]['iid']), '--title', title,
                         '--description', body] + (['--draft'] if draft else []), repo)
        else:
            output = checked_run(['glab', 'mr', 'create', '--source-branch', state['branch'],
                                  '--target-branch', state['template_base_name'], '--title', title,
                                  '--description', body, '--yes'] + (['--draft'] if draft else []), repo)
            match = re.search(r'https?://\S+/-/merge_requests/\d+', output)
            if not match:
                raise sync.ReverseSyncError('No merge request URL; branch and patch retained.')
            url = match.group()
    state['publication'] = {'url': url, 'commit': proposal, 'branch': state['branch'], 'draft': draft,
                            'decisions_hash': hashlib.sha256(json.dumps(groups, sort_keys=True).encode()).hexdigest()}
    write(workspace / 'workspace.json', state)
    return state['publication']


def checkpoint_from_review(repo, review_file, push=None, expected_remote=None):
    review_file = Path(review_file).resolve()
    workspace, state = load(review_file.parent)
    report = read(review_file)
    repo = Path(sync._git(repo, 'rev-parse', '--show-toplevel').decode().strip())
    if (str(repo) != state['project'] or report['until'] != state['until']
            or report['since'] != state['since'] or report['checkpoint'] != state['checkpoint']):
        raise sync.ReverseSyncError('Review does not match the prepared workspace and project.')
    groups = resolved_decisions(workspace, report)
    if any(g['disposition'] == 'accepted' for g in groups):
        publication = state.get('publication')
        if not publication or not publication.get('url'):
            raise sync.ReverseSyncError('Accepted changes require a durable published proposal.')
        remote_branch = sync._git(workspace / 'template', 'ls-remote', 'origin',
                                   'refs/heads/' + publication['branch']).decode().split()
        if not remote_branch or remote_branch[0] != publication['commit']:
            raise sync.ReverseSyncError('Published proposal branch changed or is missing.')
        if (sync._commit(workspace / 'template', 'HEAD') != publication['commit']
                or publication.get('decisions_hash') != hashlib.sha256(json.dumps(groups, sort_keys=True).encode()).hexdigest()):
            raise sync.ReverseSyncError('Proposal commit or dispositions changed since publication.')
        if sync._git(workspace / 'template', 'status', '--porcelain'):
            raise sync.ReverseSyncError('Unpublished template edits remain.')
    checkpoint = report['checkpoint']
    ref = checkpoint['ref']
    if not ref.startswith('refs/template-manager/'):
        raise sync.ReverseSyncError('Checkpoint refs must be under refs/template-manager/.')
    sync._git(repo, 'check-ref-format', ref)
    current = sync._optional_ref_commit(repo, ref)
    if current != checkpoint['local']:
        raise sync.ReverseSyncError('Local checkpoint changed since preparation.')
    observed = checkpoint['remote']
    if observed['remote']:
        actual = sync._remote_checkpoint(repo, observed['remote'], ref)
        if actual['status'] != observed['status'] or actual['sha'] != observed['sha']:
            raise sync.ReverseSyncError('Remote checkpoint changed or is inaccessible; reconcile first.')
    if push:
        if (push != observed['remote'] or observed['status'] not in ('present', 'absent')
                or expected_remote is None or expected_remote != (observed['sha'] or '')):
            raise sync.ReverseSyncError('--push and --expected-remote must match the recorded remote observation.')
    target = sync._commit(repo, report['until'])
    sync._ancestor(repo, report['since'], target)
    if current:
        sync._ancestor(repo, current, target)
    sync._git(repo, 'update-ref', ref, target, current or '')
    if push:
        try:
            sync._git(repo, 'push', f'--force-with-lease={ref}:{expected_remote}', push, f'{ref}:{ref}')
        except sync.ReverseSyncError as exc:
            raise sync.ReverseSyncError(f'Local checkpoint updated to {target}; remote push failed: {exc}') from exc
    return target


def preflight(repo, remote, timeout=20):
    started = time.monotonic()
    try:
        result = subprocess.run(['git', '-C', str(repo), 'ls-remote', '--refs', remote],
                                capture_output=True, text=True, timeout=timeout)
        return {'remote': remote, 'seconds': round(time.monotonic() - started, 3),
                'status': 'passed' if result.returncode == 0 else 'failed',
                'failure_kind': failure_kind(result.stderr) if result.returncode else None,
                'error': result.stderr.strip() if result.returncode else None}
    except subprocess.TimeoutExpired:
        return {'remote': remote, 'seconds': round(time.monotonic() - started, 3),
                'status': 'failed', 'failure_kind': 'timeout'}


def test_template(source, settings_file, alternate_file, workspace, run_tests=False, cache=None):
    """Run the same fixture/contract checks in template CI, without project history."""
    source, workspace = Path(source).resolve(), Path(workspace).resolve()
    if workspace.is_relative_to(source):
        raise sync.ReverseSyncError('Test workspace must be outside the template source.')
    workspace.mkdir(parents=True, exist_ok=False)
    # Copy only generator-visible files, excluding Git internals.
    for label in ('template', 'base'):
        root = workspace / label
        root.mkdir()
        for path in generator._list_of_files(source):
            target = contained(root, Path(path).relative_to(source))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    settings, alternate = toml.load(settings_file), toml.load(alternate_file)
    for key in ('date', 'uuid_seed'):
        settings.setdefault(key, '1970-01-01' if key == 'date' else 'template-test')
        alternate.setdefault(key, settings[key])
    settings.setdefault('template', str(source))
    alternate.setdefault('template', str(source))
    for label, values in (('source', settings), ('alternate', alternate)):
        (workspace / f'{label}-settings.toml').write_text(toml.dumps(values), encoding='utf-8')
    cache = Path(cache or user_cache_dir('template-manager')).resolve()
    write(workspace / 'workspace.json', {'schema_version': 1, 'folder': '.', 'cache': str(cache)})
    return validate(workspace, run_tests)
