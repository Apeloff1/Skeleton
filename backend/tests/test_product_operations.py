import json

import pytest

from core.charter_policy import CharterPolicy, Rule
from core.product_kernel import PRODUCT_KERNEL
from core.product_operations import OperationRejected, ProductOperationCoordinator


def coordinator(tmp_path, *, quorum=False):
    policy = CharterPolicy()
    policy.ratify(
        "builds",
        [Rule("build-submit", "build.submit", min_weight=2, requires_quorum=quorum)],
    )
    return ProductOperationCoordinator(tmp_path, kernel=PRODUCT_KERNEL, policy=policy)


def test_admission_stages_payload_journals_intent_and_audits(tmp_path):
    ops = coordinator(tmp_path)
    admitted = ops.admit(
        capability_id="studio",
        domain="builds",
        action="build.submit",
        principal="creator-1",
        actor_weight=2,
        payload={"title": "A", "spec": {"genre": "rpg"}},
    )
    assert admitted.capability_id == "studio"
    assert admitted.pillar == "create"
    assert admitted.outbox_seq == 1
    assert len(admitted.audit_hash) == 64
    assert ops.load_payload(admitted) == {"title": "A", "spec": {"genre": "rpg"}}
    snapshot = ops.snapshot()
    assert snapshot["pending_operations"] == 1
    assert snapshot["content_store"]["manifests"] == 1
    assert snapshot["audit_sequence"] == 1


def test_unknown_capability_rejected_before_side_effects(tmp_path):
    ops = coordinator(tmp_path)
    with pytest.raises(OperationRejected, match="unknown product capability"):
        ops.admit(
            capability_id="legacy-random-router",
            domain="builds",
            action="build.submit",
            principal="x",
            actor_weight=99,
            payload={"x": 1},
        )
    assert ops.snapshot()["pending_operations"] == 0
    assert ops.snapshot()["audit_sequence"] == 0


def test_policy_denial_is_worm_audited_but_not_journaled(tmp_path):
    ops = coordinator(tmp_path)
    with pytest.raises(OperationRejected, match="below required"):
        ops.admit(
            capability_id="studio",
            domain="builds",
            action="build.submit",
            principal="creator-low-rank",
            actor_weight=1,
            payload={"title": "denied"},
        )
    assert ops.outbox.pending_count == 0
    assert ops.store.stats()["manifests"] == 0
    assert ops.audit.latest.kind == "operation_rejected"


def test_unchartered_action_fails_closed(tmp_path):
    ops = coordinator(tmp_path)
    with pytest.raises(OperationRejected, match="not chartered"):
        ops.admit(
            capability_id="studio",
            domain="builds",
            action="build.delete_everything",
            principal="creator",
            actor_weight=100,
            payload={},
        )
    assert ops.outbox.pending_count == 0


def test_quorum_rule_requires_explicit_approval(tmp_path):
    ops = coordinator(tmp_path, quorum=True)
    kwargs = dict(
        capability_id="studio",
        domain="builds",
        action="build.submit",
        principal="creator",
        actor_weight=2,
        payload={"title": "governed"},
    )
    with pytest.raises(OperationRejected, match="quorum approval required"):
        ops.admit(**kwargs)
    admitted = ops.admit(**kwargs, quorum_approved=True)
    assert admitted.outbox_seq == 1
    assert ops.audit.sequence == 2


def test_restart_restores_pending_intent_and_audit_chain(tmp_path):
    ops = coordinator(tmp_path)
    admitted = ops.admit(
        capability_id="studio",
        domain="builds",
        action="build.submit",
        principal="creator",
        actor_weight=2,
        payload={"title": "restart-safe"},
    )

    policy = CharterPolicy()
    policy.ratify("builds", [Rule("build-submit", "build.submit", min_weight=2)])
    restored = ProductOperationCoordinator(tmp_path, kernel=PRODUCT_KERNEL, policy=policy)
    assert restored.outbox.pending_count == 1
    assert restored.audit.sequence == 1
    assert restored.load_payload(admitted)["title"] == "restart-safe"
