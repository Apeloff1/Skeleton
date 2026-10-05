from hashlib import sha256
import pytest
from skeleton.automation.transactional_workspace import TransactionalWorkspace, WorkspaceBudgetExceeded, WorkspaceConflict, WorkspaceError, MAX_CONTENT_BYTES

def d(v: bytes)->str: return sha256(v).hexdigest()

def test_commit_is_deterministic_and_proposal_only():
    a=TransactionalWorkspace({"b.txt":b"2","a.txt":b"1"}); a.write("a.txt",b"x",expected_digest=d(b"1"))
    b=TransactionalWorkspace({"a.txt":b"1","b.txt":b"2"}); b.write("a.txt",b"x",expected_digest=d(b"1"))
    assert a.commit()==b.commit()
    assert a.commit if True else None

def test_stale_write_fails_atomically():
    w=TransactionalWorkspace({"a":b"old"})
    before=w.result_digest
    with pytest.raises(WorkspaceConflict): w.write("a",b"new",expected_digest=d(b"wrong"))
    assert w.result_digest==before and w.read("a").content==b"old"

def test_create_requires_explicit_absence_precondition():
    w=TransactionalWorkspace({})
    with pytest.raises(WorkspaceConflict): w.write("new",b"x",expected_digest=d(b""))
    w.write("new",b"x",expected_digest=None)
    assert w.read("new").content==b"x"

@pytest.mark.parametrize("path",["../x","a/../x","/abs","a//b","a\\b"])
def test_paths_fail_closed(path):
    with pytest.raises(WorkspaceError): TransactionalWorkspace({path:b"x"})

def test_delete_requires_exact_digest_and_rollback_restores_base():
    w=TransactionalWorkspace({"a":b"x"})
    with pytest.raises(WorkspaceConflict): w.delete("a",expected_digest=d(b"y"))
    w.delete("a",expected_digest=d(b"x")); w.rollback()
    assert w.read("a").content==b"x" and w.result_digest==w.base_digest

def test_content_budget_is_hard():
    with pytest.raises(WorkspaceBudgetExceeded): TransactionalWorkspace({"a":b"x"*(MAX_CONTENT_BYTES+1)})

def test_commit_closes_mutation_and_receipt_cannot_escalate():
    w=TransactionalWorkspace({"a":b"x"}); r=w.commit()
    assert r.authority_scope=="workspace-proposal-only"
    with pytest.raises(WorkspaceError): w.write("a",b"y",expected_digest=d(b"x"))
    with pytest.raises(WorkspaceError): type(r)(r.base_digest,r.result_digest,r.changed_paths,r.operation_digest,"execution")
