"""Integration coverage for the automated pipeline using local Git repositories."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import pytest
import toml

from template_manager import project_from_template as gen
from template_manager import reverse_sync as sync
from template_manager import reverse_workspace as flow
from test_reverse_sync import git, init, commit


@pytest.fixture
def workspace(tmp_path):
    template = tmp_path / 'template'
    init(template)
    git(template, 'checkout', '-b', 'main')
    (template / '%project_snake%.txt').write_text('name=%project%\nold literal\nend\n')
    sha = commit(template)
    repo = tmp_path / 'project'
    init(repo)
    settings = {'template': str(template), 'git_commit': sha, 'project': 'Demo',
                'git_folder': '.', 'uuid_seed': 'stable', 'template_syntax': 'legacy'}
    (repo / sync.SETTINGS).write_text(toml.dumps(settings))
    (repo / 'demo.txt').write_text('name=Demo\nold literal\nend\n')
    before = commit(repo)
    (repo / 'demo.txt').write_text('name=Demo\nnew literal\nend\n')
    after = commit(repo)
    output = tmp_path / 'review'
    flow.prepare(repo, output, since=before, until=after, remote='', cache=tmp_path / 'cache')
    return output, repo, before, after


def accept(output):
    decisions = flow.read(output / 'decisions.json')
    for group in decisions['groups']:
        group['disposition'] = 'accepted'
    flow.write(output / 'decisions.json', decisions)


def test_prepare_apply_validate_preserves_parameters_and_source(workspace):
    output, repo, before, after = workspace
    state = flow.read(output / 'workspace.json')
    assert state['since'] == before and state['until'] == after
    assert sync._optional_ref_commit(repo, sync.DEFAULT_REF) is None
    accept(output)
    result = flow.apply(output)
    assert result['groups'][0]['application'] == 'applied'
    target = output / 'template' / '%project_snake%.txt'
    assert target.read_text() == 'name=%project%\nnew literal\nend\n'
    assert flow.apply(output) == result
    result = flow.validate(output)
    assert result['passed']
    assert result['test_status'] == 'not-declared'
    assert (repo / 'demo.txt').read_text() == 'name=Demo\nnew literal\nend\n'
    assert (output / 'validation.md').exists()
    assert not any('baseline_test' in f for f in result['fixtures'])


def test_apply_requires_explicit_acceptance(workspace):
    output, *_ = workspace
    flow.apply(output)
    assert 'old literal' in (output / 'template' / '%project_snake%.txt').read_text()


@pytest.mark.parametrize('new', ['name=Other\nnew literal\nend\n', 'name=Demo\nnew Demo\nend\n'])
def test_ambiguous_edits_are_not_written(workspace, new):
    output, repo, _, _ = workspace
    (repo / 'demo.txt').write_text(new)
    after = commit(repo)
    state = flow.read(output / 'workspace.json')
    state['until'] = after
    flow.write(output / 'workspace.json', state)
    accept(output)
    result = flow.apply(output)
    assert result['groups'][0]['application'] == 'requires-review'
    assert 'old literal' in (output / 'template' / '%project_snake%.txt').read_text()


def test_current_upstream_edits_block_automatic_application(workspace):
    output, *_ = workspace
    accept(output)
    target = output / 'template' / '%project_snake%.txt'
    target.write_text(target.read_text() + 'upstream\n')
    result = flow.apply(output)
    assert result['groups'][0]['application'] == 'requires-review'
    assert target.read_text().endswith('upstream\n')


def contract(output, script):
    for tree in ('base', 'template'):
        root = output / tree
        (root / 'check.py').write_text(script)
        (root / '.template-tests.toml').write_text(toml.dumps({
            'command': [sys.executable, '{template}/check.py'], 'timeout': 5}))


def test_baseline_only_runs_on_failure_and_classifies_existing_defect(workspace):
    output, *_ = workspace
    contract(output, "import sys\nprint('existing build defect')\nsys.exit(1)\n")
    with pytest.raises(sync.ReverseSyncError, match='--run-tests'):
        flow.validate(output)
    result = flow.validate(output, run_tests=True)
    assert not result['passed']
    assert {f['classification'] for f in result['fixtures']} == {'pre-existing-failure'}
    assert all(f['baseline_test']['returncode'] == 1 for f in result['fixtures'])


def test_regression_vs_environment_failure(workspace):
    output, *_ = workspace
    contract(output, "print('OK')\n")
    script = output / 'template' / 'check.py'
    script.write_text("import sys\nprint('broken')\nsys.exit(1)\n")
    assert {f['classification'] for f in flow.validate(output, True)['fixtures']} == {'regression'}
    script.write_text("import sys\nprint('certificate verify failed')\nsys.exit(1)\n")
    assert {f['classification'] for f in flow.validate(output, True)['fixtures']} == {'environment/network-failure'}


def test_alternate_name_and_content_leaks(workspace):
    output, *_ = workspace
    (output / 'template' / 'Demo.cfg').write_text('Demo\n')
    result = flow.validate(output)
    alternate = result['fixtures'][1]
    assert alternate['classification'] == 'regression'
    assert any(f['kind'] == 'source-value-leak' for f in alternate['findings'])


def test_publish_requires_fresh_validation_and_resolved_decisions(workspace):
    output, *_ = workspace
    with pytest.raises(sync.ReverseSyncError, match='dispositions'):
        flow.publish(output)
    accept(output)
    flow.validate(output)
    target = output / 'template' / '%project_snake%.txt'
    target.write_text(target.read_text() + 'later edit\n')
    with pytest.raises(sync.ReverseSyncError, match='changed since validation'):
        flow.publish(output)


def test_checkpoint_requires_durable_accepted_changes(workspace):
    output, repo, *_ = workspace
    accept(output)
    with pytest.raises(sync.ReverseSyncError, match='durable'):
        flow.checkpoint_from_review(repo, output / 'review.json')
    assert sync._optional_ref_commit(repo, sync.DEFAULT_REF) is None


def exclude(output):
    decisions = flow.read(output / 'decisions.json')
    for group in decisions['groups']:
        group['disposition'] = 'excluded'
    flow.write(output / 'decisions.json', decisions)


def test_checkpoint_exact_until_and_stale_local_detection(workspace):
    output, repo, before, after = workspace
    exclude(output)
    sync.mark_reviewed(repo, before)
    with pytest.raises(sync.ReverseSyncError, match='Local checkpoint changed'):
        flow.checkpoint_from_review(repo, output / 'review.json')
    git(repo, 'update-ref', '-d', sync.DEFAULT_REF)
    (repo / 'extra').write_text('later')
    latest = commit(repo)
    assert flow.checkpoint_from_review(repo, output / 'review.json') == after
    assert git(repo, 'rev-parse', sync.DEFAULT_REF) == after != latest


def test_checkpoint_rejects_missing_inventory_entries(workspace):
    output, repo, *_ = workspace
    flow.write(output / 'decisions.json', {'groups': []})
    with pytest.raises(sync.ReverseSyncError, match='every review entry'):
        flow.checkpoint_from_review(repo, output / 'review.json')


def test_remote_checkpoint_lease_and_changed_remote(workspace, tmp_path):
    output, repo, before, after = workspace
    remote = tmp_path / 'remote.git'
    subprocess.check_call(['git', 'init', '--bare', '-q', str(remote)])
    git(repo, 'remote', 'add', 'origin', str(remote))
    exclude(output)
    report = flow.read(output / 'review.json')
    state = flow.read(output / 'workspace.json')
    observed = {'remote': 'origin', 'status': 'absent', 'sha': None}
    report['checkpoint']['remote'] = state['checkpoint']['remote'] = observed
    flow.write(output / 'review.json', report)
    flow.write(output / 'workspace.json', state)
    with pytest.raises(sync.ReverseSyncError, match='expected-remote'):
        flow.checkpoint_from_review(repo, output / 'review.json', push='origin')
    git(repo, 'push', 'origin', f'{before}:{sync.DEFAULT_REF}')
    with pytest.raises(sync.ReverseSyncError, match='Remote checkpoint changed'):
        flow.checkpoint_from_review(repo, output / 'review.json', push='origin', expected_remote='')
    git(remote, 'update-ref', '-d', sync.DEFAULT_REF)
    flow.checkpoint_from_review(repo, output / 'review.json', push='origin', expected_remote='')
    assert git(remote, 'rev-parse', sync.DEFAULT_REF) == after


def test_render_manifest_mapping_hashes_and_cache(workspace, tmp_path):
    output, *_ = workspace
    manifest = flow.read(output / 'original-render' / flow.MANIFEST)
    entry = next(f for f in manifest['files'] if f['rendered_path'] == 'demo.txt')
    assert entry['template_path'] == '%project_snake%.txt'
    assert len(entry['template_hash']) == len(entry['rendered_hash']) == 64
    source = output / 'template'
    settings = toml.load(output / 'source-settings.toml')
    first = flow.render(source, settings, tmp_path / 'one', tmp_path / 'cache2')
    assert flow.render(source, settings, tmp_path / 'two', tmp_path / 'cache2') == first
    (source / '%project_snake%.txt').write_text('changed %project%\n')
    assert flow.render(source, settings, tmp_path / 'three', tmp_path / 'cache2') != first


def test_preflight_failure_classification():
    assert flow.failure_kind('X.509 certificate bundle information') is None
    assert flow.failure_kind('fatal: Could not resolve host: example.test') == 'dns'
    assert flow.failure_kind('Authentication failed') == 'authentication'


def test_settings_project_override(workspace, tmp_path):
    output, *_ = workspace
    defaults = {'default_template_repo': None, 'author': None, 'email': None}
    args = gen._parse_command_line_arguments(['Another Name', '-t', str(output / 'source-settings.toml'),
                                              '-o', str(tmp_path / 'renamed'), '--no-gitlab-project'], defaults)
    result = gen._build(args, template_path=output / 'template')
    assert (result / 'another_name.txt').exists()
    assert 'name=Another Name' in (result / 'another_name.txt').read_text()


def test_publish_creates_and_updates_proposal_and_checkpoint(workspace, monkeypatch):
    output, repo, _, after = workspace
    accept(output)
    flow.apply(output)
    flow.validate(output)
    proposal_repo = output / 'template'
    git(proposal_repo, 'config', 'user.name', 'Test')
    git(proposal_repo, 'config', 'user.email', 'test@example.com')
    original_run = flow.checked_run
    calls = []
    existing = []
    def run(argv, cwd):
        if argv[0] != 'gh':
            return original_run(argv, cwd)
        calls.append(argv)
        if argv[1:3] == ['pr', 'list']:
            return json.dumps(existing)
        return 'https://github.com/example/templates/pull/1'
    monkeypatch.setattr(flow, 'checked_run', run)
    result = flow.publish(output, provider='github')
    assert result['url'].endswith('/pull/1')
    assert (output / 'template.patch').read_bytes().startswith(b'diff --git')
    assert flow.read(output / 'workspace.json')['publication'] == result
    existing.append({'url': result['url']})
    flow.publish(output, provider='github')
    assert any(argv[1:3] == ['pr', 'edit'] for argv in calls)
    assert flow.checkpoint_from_review(repo, output / 'review.json') == after


def test_template_ci_runner_and_fresh_outputs(workspace, tmp_path):
    output, *_ = workspace
    contract(output, "from pathlib import Path\np = Path('previous-test-output')\nassert not p.exists()\np.write_text('done')\n")
    for n in (1, 2):
        result = flow.test_template(output / 'template', output / 'source-settings.toml',
                                    output / 'alternate-settings.toml', tmp_path / f'ci-{n}',
                                    run_tests=True, cache=tmp_path / 'ci-cache')
        assert result['passed'] and result['test_status'] == 'executed'


def test_conditional_template_requires_manual_patch(workspace):
    output, *_ = workspace
    accept(output)
    for label in ('original', 'template'):
        target = output / label / '%project_snake%.txt'
        target.write_text(target.read_text() + '%if(flag)%\nconditional\n%endif%\n')
    result = flow.apply(output)
    assert result['groups'][0]['application'] == 'requires-review'
    assert 'Conditional' in result['groups'][0]['reason']


def test_prepare_never_reuses_existing_workspace(workspace):
    output, repo, before, after = workspace
    with pytest.raises(FileExistsError):
        flow.prepare(repo, output, since=before, until=after, remote='')
    assert (output / 'workspace.json').exists()


def test_test_contract_uses_rendered_parameter_values(workspace):
    output, *_ = workspace
    script = "import sys\nfrom pathlib import Path\nassert Path(sys.argv[1].lower().replace(' ', '_') + '.txt').exists()\n"
    contract(output, script)
    for tree in ('base', 'template'):
        (output / tree / '.template-tests.toml').write_text(toml.dumps({
            'command': [sys.executable, '{template}/check.py', '%project%']}))
    assert flow.validate(output, True)['passed']


def test_cli_validation_exit_status(workspace):
    output, repo, *_ = workspace
    (output / 'template' / 'leak.txt').write_text('Demo')
    assert sync.main(['-d', str(repo), 'validate', '--workspace', str(output)]) == 1


def test_mapping_manifest_avoids_historical_rerender(workspace, monkeypatch):
    output, repo, _, _ = workspace
    state = flow.read(output / 'workspace.json')
    manifest = flow.read(output / 'original-render' / flow.MANIFEST)
    manifest['template_revision'] = state['pinned_template']
    (repo / flow.MANIFEST).write_text(json.dumps(manifest))
    before = commit(repo)
    (repo / 'demo.txt').write_text('newer literal\n')
    commit(repo)
    def unexpected(*args):
        raise AssertionError('Compatible manifest should avoid historical rendering')
    monkeypatch.setattr(sync, '_template_paths', unexpected)
    _, report = sync.extract(repo, since=before)
    assert report['files'][0]['reasons'] == ['template-path']


def test_publish_rejects_changed_fixture_settings(workspace):
    output, *_ = workspace
    accept(output)
    flow.validate(output)
    path = output / 'alternate-settings.toml'
    settings = toml.load(path)
    settings['project'] = 'Changed After Validation'
    path.write_text(toml.dumps(settings))
    with pytest.raises(sync.ReverseSyncError, match='changed since validation'):
        flow.publish(output)
