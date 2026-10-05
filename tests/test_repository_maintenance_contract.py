from __future__ import annotations
import hashlib,pytest
from skeleton.automation.repository_maintenance import *
SHA=hashlib.sha256(b"resource").hexdigest()
def owner(**kw):
 v=dict(resource_id="RESOURCE.STALE.1",kind=ResourceKind.BRANCH,ownership=OwnershipClass.UNOWNED,owner="repo-maintainer",retention_reason="retention window elapsed",active_refs=());v.update(kw);return RepositoryOwnership(**v)
def task(**kw):
 v=dict(task_id="TASK.CLEAN.1",resource_id="RESOURCE.STALE.1",action=MaintenanceAction.DELETE,risk=MaintenanceRisk.HIGH,expected_digest=SHA,mutation_limit=1);v.update(kw);return MaintenanceTask(**v)
def evidence(**kw):
 v=dict(evidence_id="EVID.CLEAN.1",resource_id="RESOURCE.STALE.1",observed_digest=SHA,reachable=False,retention_satisfied=True,active_migration=False,release_bound=False,evidence_bound=False);v.update(kw);return ResourceEvidence(**v)
def test_safe_unowned_unreachable_expired_resource_can_be_authorized():
 assert authorize(task(),owner(),evidence()).decision is MaintenanceDecision.ALLOW
def test_delete_without_evidence_fails_closed():
 r=authorize(task(),owner());assert r.decision is MaintenanceDecision.BLOCK;assert "missing_resource_evidence" in r.reasons
@pytest.mark.parametrize("ownership",[OwnershipClass.ACTIVE,OwnershipClass.MIGRATION,OwnershipClass.RELEASE,OwnershipClass.EVIDENCE])
def test_protected_ownership_blocks_deletion(ownership):
 assert authorize(task(),owner(ownership=ownership),evidence()).decision is MaintenanceDecision.BLOCK
def test_generated_resource_is_not_implicitly_protected_but_still_requires_evidence():
 assert authorize(task(),owner(ownership=OwnershipClass.GENERATED),evidence()).decision is MaintenanceDecision.ALLOW
def test_active_reference_blocks_deletion():
 o=owner(ownership=OwnershipClass.ACTIVE,active_refs=("PR.2790",));assert "active_references" in authorize(task(),o,evidence()).reasons
def test_reachability_blocks_deletion():
 assert "resource_reachable" in authorize(task(),owner(),evidence(reachable=True)).reasons
def test_retention_blocks_deletion():
 assert "retention_not_satisfied" in authorize(task(),owner(),evidence(retention_satisfied=False)).reasons
@pytest.mark.parametrize("field,reason",[("active_migration","active_migration"),("release_bound","release_bound"),("evidence_bound","evidence_bound")])
def test_special_bindings_block_deletion(field,reason):
 assert reason in authorize(task(),owner(),evidence(**{field:True})).reasons
def test_changed_resource_digest_blocks_stale_cleanup():
 other=hashlib.sha256(b"changed").hexdigest();assert "resource_changed_since_observation" in authorize(task(),owner(),evidence(observed_digest=other)).reasons
def test_deletion_cannot_be_low_risk():
 with pytest.raises(MaintenanceError,match="below high"):task(risk=MaintenanceRisk.LOW)
def test_mutation_budget_is_bounded():
 with pytest.raises(MaintenanceError,match="bounded"):task(mutation_limit=101)
def test_cross_resource_evidence_rejected():
 with pytest.raises(MaintenanceError,match="resource evidence mismatch"):authorize(task(),owner(),evidence(resource_id="RESOURCE.OTHER.1"))
def test_receipt_binds_task_ownership_and_evidence():
 r=authorize(task(),owner(),evidence());assert r.task_digest==task().digest;assert r.ownership_digest==owner().digest;assert r.evidence_digest==evidence().digest
