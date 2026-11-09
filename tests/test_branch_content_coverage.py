"""Real Git repository fixtures; no network and no destructive branch operations."""
import subprocess
import pytest
from scripts.audit_branch_content_coverage import audit, AuditError


def git(repo, *args):
    return subprocess.run(['git', *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo, msg):
    git(repo, 'add', '-A')
    git(repo, 'commit', '-m', msg)
    return git(repo, 'rev-parse', 'HEAD')


def fixture(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.email', 'test@example.test')
    git(repo, 'config', 'user.name', 'Tester')
    (repo / 'base.py').write_text('x = 1\n')
    initial = commit(repo, 'base')
    git(repo, 'checkout', '-b', 'old')
    (repo / 'new.py').write_text('value = 2\n')
    commit(repo, 'legacy change')
    git(repo, 'checkout', 'main')
    (repo / 'new.py').write_text('value = 2\n')
    (repo / 'other.py').write_text('modern = True\n')
    commit(repo, 'modern equivalent')
    return repo, initial


def test_divergent_history_can_be_content_covered(tmp_path):
    repo, _ = fixture(tmp_path)
    out = audit(repo, main_ref='refs/heads/main', branch_refs=['refs/heads/old'])
    old = out['branches'][0]
    assert old['changed_paths'] == 1
    assert old['counts'] == {'byte_identical': 1}
    assert old['all_changed_paths_byte_identical_to_main']
    assert not old['requires_manual_review']
    assert not out['deletion_authorized'] and not out['merging_authorized']
    assert 'new.py' in old['paths'][0]['path']


def test_distinguish_modified_missing_and_deleted_paths(tmp_path):
    repo, _ = fixture(tmp_path)
    git(repo, 'checkout', 'old')
    (repo / 'new.py').write_text('value = 3\n')
    (repo / 'separate.py').write_text('legacy only\n')
    (repo / 'base.py').unlink()
    commit(repo, 'diverged changes')
    out = audit(repo, main_ref='refs/heads/main', branch_refs=['refs/heads/old'])['branches'][0]
    assert out['counts'] == {'different_content_or_mode': 1,
                             'missing_on_main': 1,
                             'removed_on_branch_present_on_main': 1}
    assert out['requires_manual_review']
    assert not out['all_changed_paths_byte_identical_to_main']


def test_invalid_ref_and_wrong_bounds_fail_closed(tmp_path):
    repo, _ = fixture(tmp_path)
    with pytest.raises(AuditError):
        audit(repo, main_ref='refs/heads/main', branch_refs=['refs/heads/../old'])
    with pytest.raises(AuditError):
        audit(repo, main_ref='refs/heads/main', branch_refs=['refs/heads/old'], max_paths=0)
    with pytest.raises(AuditError):
        audit(repo, main_ref='refs/heads/main', branch_refs=['refs/heads/old'], max_paths=0.5)
    with pytest.raises(AuditError):
        audit(repo, main_ref='refs/heads/main', branch_refs=[])


def test_executable_mode_change_needs_review(tmp_path):
    repo, _ = fixture(tmp_path)
    git(repo, 'checkout', 'old')
    (repo / 'new.py').chmod(0o755)
    commit(repo, 'executable mode')
    out = audit(repo, main_ref='refs/heads/main', branch_refs=['refs/heads/old'])['branches'][0]
    assert out['counts'] == {'different_content_or_mode': 1}
    assert out['paths'][0]['branch_mode'] != out['paths'][0]['main_mode']
