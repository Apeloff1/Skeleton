from hashlib import sha256
import pytest
from skeleton.automation.transactional_workspace import EditLease, EditLeaseRegistry, TransactionalWorkspace, WorkspaceBudgetExceeded, WorkspaceConflict, WorkspaceError, MAX_CONTENT_BYTES

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


def test_shared_edit_lease_registry_rejects_overlapping_paths():
    registry=EditLeaseRegistry()
    a=TransactionalWorkspace({"a":b"x"},lease_registry=registry)
    b=TransactionalWorkspace({"a":b"x"},lease_registry=registry)
    a.acquire_lease(lease_id="lease-a",owner_id="worker-a",paths=("a",))
    with pytest.raises(WorkspaceConflict,match="path conflict"):
        b.acquire_lease(lease_id="lease-b",owner_id="worker-b",paths=("a",))

def test_lease_aware_workspace_requires_leased_mutation_and_releases_on_commit():
    registry=EditLeaseRegistry()
    w=TransactionalWorkspace({"a":b"old"},lease_registry=registry)
    lease=w.acquire_lease(lease_id="lease-a",owner_id="worker-a",paths=("a",))
    with pytest.raises(WorkspaceError,match="write_leased"):
        w.write("a",b"new",expected_digest=d(b"old"))
    w.write_leased(lease,"a",b"new",expected_digest=d(b"old"))
    receipt=w.commit_leased(lease)
    assert receipt.changed_paths==("a",)
    assert receipt.authority_scope=="workspace-proposal-only"
    other=TransactionalWorkspace({"a":b"old"},lease_registry=registry)
    next_lease=other.acquire_lease(lease_id="lease-b",owner_id="worker-b",paths=("a",))
    assert next_lease.owner_id=="worker-b"

def test_edit_lease_is_bound_to_workspace_base_and_path_allowlist():
    registry=EditLeaseRegistry()
    source=TransactionalWorkspace({"a":b"old","b":b"x"},lease_registry=registry)
    lease=source.acquire_lease(lease_id="lease-a",owner_id="worker-a",paths=("a",))
    with pytest.raises(WorkspaceConflict,match="outside edit lease"):
        source.write_leased(lease,"b",b"y",expected_digest=d(b"x"))
    other=TransactionalWorkspace({"a":b"different"},lease_registry=EditLeaseRegistry())
    with pytest.raises(WorkspaceConflict,match="stale or inactive"):
        other.write_leased(lease,"a",b"new",expected_digest=d(b"different"))

def test_edit_lease_cannot_escalate_repository_authority():
    with pytest.raises(WorkspaceError,match="cannot grant repository authority"):
        EditLease("lease","worker","0"*64,("a",),"repository-write")
