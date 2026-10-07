import asyncio
import json

import pytest

from core.charter_policy import CharterPolicy, Rule
from core.durable_outbox import OutboxFullError
from core.product_kernel import PRODUCT_KERNEL
from core.product_operations import OperationExecutionError, OperationRejected, ProductOperationCoordinator


def coordinator(tmp_path, *, quorum=False, outbox_cap=4096):
    policy = CharterPolicy()
    policy.ratify("builds", [Rule("build-submit", "build.submit", min_weight=2, requires_quorum=quorum)])
    return ProductOperationCoordinator(tmp_path, kernel=PRODUCT_KERNEL, policy=policy, outbox_cap=outbox_cap)


def test_admission_stages_payload_journals_intent_and_audits(tmp_path):
    ops = coordinator(tmp_path)
    admitted = ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator-1",
                         actor_weight=2, payload={"title": "A", "spec": {"genre": "rpg"}})
    assert admitted.capability_id == "studio" and admitted.pillar == "create" and admitted.outbox_seq == 1
    assert len(admitted.audit_hash) == 64
    assert ops.load_payload(admitted) == {"title": "A", "spec": {"genre": "rpg"}}
    snapshot = ops.snapshot()
    assert snapshot["pending_operations"] == 1 and snapshot["outbox_capacity_remaining"] == 4095
    assert snapshot["content_store"]["manifests"] == 1 and snapshot["audit_sequence"] == 1
    assert snapshot["admission_cross_process_locking"] is True


def test_unknown_capability_rejected_before_side_effects(tmp_path):
    ops = coordinator(tmp_path)
    with pytest.raises(OperationRejected, match="unknown product capability"):
        ops.admit(capability_id="legacy-random-router", domain="builds", action="build.submit", principal="x", actor_weight=99, payload={"x": 1})
    assert ops.snapshot()["pending_operations"] == 0 and ops.snapshot()["audit_sequence"] == 0


def test_policy_denial_is_worm_audited_but_not_journaled(tmp_path):
    ops = coordinator(tmp_path)
    with pytest.raises(OperationRejected, match="below required"):
        ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator-low-rank", actor_weight=1, payload={"title": "denied"})
    assert ops.outbox.pending_count == 0 and ops.store.stats()["manifests"] == 0
    assert ops.audit.latest.kind == "operation_rejected"


def test_unchartered_action_fails_closed(tmp_path):
    ops = coordinator(tmp_path)
    with pytest.raises(OperationRejected, match="not chartered"):
        ops.admit(capability_id="studio", domain="builds", action="build.delete_everything", principal="creator", actor_weight=100, payload={})
    assert ops.outbox.pending_count == 0


def test_quorum_rule_requires_explicit_approval(tmp_path):
    ops = coordinator(tmp_path, quorum=True)
    kwargs = dict(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2, payload={"title": "governed"})
    with pytest.raises(OperationRejected, match="quorum approval required"): ops.admit(**kwargs)
    admitted = ops.admit(**kwargs, quorum_approved=True)
    assert admitted.outbox_seq == 1 and ops.audit.sequence == 2


def test_restart_restores_pending_intent_and_audit_chain(tmp_path):
    ops = coordinator(tmp_path)
    admitted = ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2, payload={"title": "restart-safe"})
    restored = coordinator(tmp_path)
    assert restored.outbox.pending_count == 1 and restored.audit.sequence == 1
    assert restored.load_payload(admitted)["title"] == "restart-safe"


def test_outbox_capacity_lease_prevents_orphan_artifact(tmp_path):
    ops = coordinator(tmp_path, outbox_cap=1)
    ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2, payload={"title": "first"})
    before = ops.store.stats()
    with pytest.raises(OutboxFullError, match="backpressured"):
        ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2, payload={"title": "second"})
    assert ops.store.stats() == before and ops.outbox.pending_count == 1


def test_idempotency_key_returns_original_operation_without_duplicate_work(tmp_path):
    ops = coordinator(tmp_path)
    kwargs = dict(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2,
                  payload={"title": "retry-safe"}, idempotency_key="client-request-42")
    first = ops.admit(**kwargs); second = ops.admit(**kwargs)
    assert second == first and ops.outbox.pending_count == 1 and ops.store.stats()["manifests"] == 1
    restored = coordinator(tmp_path); third = restored.admit(**kwargs)
    assert third == first and restored.outbox.pending_count == 1


def test_two_coordinators_share_idempotency_index_under_process_lease(tmp_path):
    left = coordinator(tmp_path); right = coordinator(tmp_path)
    kwargs = dict(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2,
                  payload={"title": "one operation"}, idempotency_key="global-key")
    first = left.admit(**kwargs); second = right.admit(**kwargs)
    assert second == first
    assert left.outbox.pending_count == right.outbox.pending_count == 1
    assert left.store.stats()["manifests"] == 1
    assert right.snapshot()["idempotency_records"] == 1


def test_idempotency_index_checksum_tampering_fails_closed(tmp_path):
    ops = coordinator(tmp_path)
    ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2, payload={"title": "safe"}, idempotency_key="safe-key")
    path = tmp_path / "operation-index.json"; envelope = json.loads(path.read_text())
    envelope["records"]["safe-key"]["principal"] = "attacker"; path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(OperationRejected, match="checksum mismatch"): coordinator(tmp_path)


def test_idempotency_index_version_mismatch_fails_closed(tmp_path):
    ops = coordinator(tmp_path)
    ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2, payload={"title": "safe"}, idempotency_key="safe-key")
    path = tmp_path / "operation-index.json"; envelope = json.loads(path.read_text())
    envelope["version"] = 999; path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(OperationRejected, match="unsupported"): coordinator(tmp_path)


def test_executor_success_confirms_only_after_side_effect(tmp_path):
    ops = coordinator(tmp_path)
    admitted = ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2, payload={"title": "execute-me"})
    seen = []
    async def executor(operation, payload): seen.append((operation.id, payload["title"], ops.outbox.pending_count)); return True
    result = asyncio.run(ops.execute_one(admitted.outbox_seq, executor))
    assert result.executed is True and result.confirmed is True
    assert seen == [(admitted.id, "execute-me", 1)] and ops.outbox.pending_count == 0 and ops.audit.latest.kind == "operation_executed"


def test_executor_false_defers_and_keeps_pending(tmp_path):
    ops = coordinator(tmp_path)
    admitted = ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2, payload={"title": "later"})
    result = asyncio.run(ops.execute_one(admitted.outbox_seq, lambda operation, payload: False))
    assert result.executed is False and result.confirmed is False and ops.outbox.pending_count == 1
    assert ops.audit.latest.kind == "operation_execution_deferred"


def test_executor_exception_is_audited_and_pending_work_survives(tmp_path):
    ops = coordinator(tmp_path)
    admitted = ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2, payload={"title": "explode"})
    def explode(operation, payload): raise RuntimeError("boom")
    with pytest.raises(OperationExecutionError, match="executor raised"): asyncio.run(ops.execute_one(admitted.outbox_seq, explode))
    assert ops.outbox.pending_count == 1 and ops.audit.latest.kind == "operation_execution_failed"


def test_pending_operations_rehydrate_execution_contract(tmp_path):
    ops = coordinator(tmp_path)
    admitted = ops.admit(capability_id="studio", domain="builds", action="build.submit", principal="creator", actor_weight=2,
                         payload={"title": "pending"}, idempotency_key="pending-1")
    pending = ops.pending_operations()
    assert len(pending) == 1 and pending[0].id == admitted.id and pending[0].idempotency_key == "pending-1"
