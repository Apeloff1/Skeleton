"""AI governance, quarantine, review queue, migration, and rollout tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.policy_migration import AIPolicyChangeRisk, AIPolicyMigrationPlanner
from skeleton.shells.ai.policy_rollout import AIPolicyRolloutManager, AIPolicyRolloutPhase
from skeleton.shells.ai.policy_store import AIPolicyStore
from skeleton.shells.ai.quarantine import AIQuarantine, QuarantineTarget
from skeleton.shells.ai.review import AIReviewView, ReviewAction
from skeleton.shells.ai.review_queue import AIReviewQueue, ReviewQueueConflict, ReviewState


def review():
    return AIReviewView(
        intent_id="i",
        goal="do work",
        proposal_id="p",
        proposal_fingerprint="a" * 64,
        model_id="m",
        confidence=0.9,
        uncertainty=0.1,
        risk_score=10,
        risk_band="low",
        requires_approval=True,
        policy_reasons=("approval required",),
        guardrail_findings=(),
        assumptions=(),
        actions=(
            ReviewAction(
                "a",
                "python",
                ("-V",),
                None,
                (),
                1,
                ("read_filesystem",),
                True,
                "",
                (),
                False,
            ),
        ),
    )


def test_quarantine_model_active():
    quarantine = AIQuarantine()
    quarantine.quarantine(
        QuarantineTarget.MODEL,
        "m",
        reason="incident",
        actor="operator",
    )
    assert quarantine.active(QuarantineTarget.MODEL, "m")


def test_quarantine_expiry():
    now = [0.0]
    quarantine = AIQuarantine(clock=lambda: now[0])
    quarantine.quarantine(
        QuarantineTarget.MODEL,
        "m",
        reason="temporary",
        actor="operator",
        ttl_seconds=1,
    )
    now[0] = 1
    assert not quarantine.active(QuarantineTarget.MODEL, "m")


def test_quarantine_release():
    quarantine = AIQuarantine()
    quarantine.quarantine(
        QuarantineTarget.COMMAND,
        "python",
        reason="bad contract",
        actor="operator",
    )
    assert quarantine.release(QuarantineTarget.COMMAND, "python")
    assert not quarantine.active(QuarantineTarget.COMMAND, "python")


def test_review_queue_claim_and_approve():
    queue = AIReviewQueue()
    item = queue.enqueue(review())
    claimed = queue.claim(item.item_id, "alice")
    decided = queue.decide(
        item.item_id,
        claim_id=claimed.claim_id,
        approve=True,
        reason="reviewed",
    )
    assert decided.state is ReviewState.APPROVED
    assert decided.reviewer == "alice"


def test_review_queue_stale_claim_rejected():
    queue = AIReviewQueue()
    item = queue.enqueue(review())
    claimed = queue.claim(item.item_id, "alice")
    with pytest.raises(ReviewQueueConflict):
        queue.decide(
            item.item_id,
            claim_id="wrong",
            approve=True,
        )
    assert queue.get(item.item_id).claim_id == claimed.claim_id


def test_review_queue_double_claim_rejected():
    queue = AIReviewQueue()
    item = queue.enqueue(review())
    queue.claim(item.item_id, "alice")
    with pytest.raises(ReviewQueueConflict):
        queue.claim(item.item_id, "bob")


def test_review_queue_expiry():
    now = [0.0]
    queue = AIReviewQueue(clock=lambda: now[0])
    item = queue.enqueue(review(), ttl_seconds=1)
    now[0] = 1
    assert queue.get(item.item_id).state is ReviewState.EXPIRED


def test_migration_max_actions_widen_review():
    planner = AIPolicyMigrationPlanner()
    migration = planner.compare(
        AIShellPolicy(max_actions=10),
        AIShellPolicy(max_actions=20),
    )
    assert any(
        item.code == "max_actions_widened"
        and item.risk is AIPolicyChangeRisk.REVIEW
        for item in migration.changes
    )


def test_migration_confidence_narrow_safe():
    planner = AIPolicyMigrationPlanner()
    migration = planner.compare(
        AIShellPolicy(min_confidence=0.5),
        AIShellPolicy(min_confidence=0.8),
    )
    assert any(
        item.code == "confidence_narrowed"
        and item.risk is AIPolicyChangeRisk.SAFE
        for item in migration.changes
    )


def test_migration_reversibility_relax_review():
    planner = AIPolicyMigrationPlanner()
    migration = planner.compare(
        AIShellPolicy(require_reversible_for_autonomy=True),
        AIShellPolicy(require_reversible_for_autonomy=False),
    )
    assert any(item.code == "reversibility_relaxed" for item in migration.changes)


def test_policy_rollout_canary_selection_deterministic():
    store = AIPolicyStore()
    manager = AIPolicyRolloutManager(store)
    manager.prepare(
        "r",
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS),
        canary_percent=50,
    )
    manager.advance("r")
    assert manager.selected("r", "alice") == manager.selected("r", "alice")


def test_policy_rollout_zero_canary_selects_none():
    store = AIPolicyStore()
    manager = AIPolicyRolloutManager(store)
    manager.prepare("r", AIShellPolicy(max_actions=31), canary_percent=0)
    manager.advance("r")
    assert not manager.selected("r", "alice")


def test_policy_rollout_hundred_canary_selects_all():
    store = AIPolicyStore()
    manager = AIPolicyRolloutManager(store)
    manager.prepare("r", AIShellPolicy(max_actions=31), canary_percent=100)
    manager.advance("r")
    assert manager.selected("r", "alice")
    assert manager.selected("r", "bob")


def test_policy_rollout_advances_to_complete():
    store = AIPolicyStore()
    manager = AIPolicyRolloutManager(store)
    manager.prepare("r", AIShellPolicy(max_actions=31))
    assert manager.advance("r").phase is AIPolicyRolloutPhase.CANARY
    assert manager.advance("r").phase is AIPolicyRolloutPhase.BROAD
    assert manager.advance("r").phase is AIPolicyRolloutPhase.COMPLETE


def test_policy_rollout_rollback_restores_base():
    base = AIShellPolicy(max_actions=32)
    store = AIPolicyStore(base)
    manager = AIPolicyRolloutManager(store)
    manager.prepare("r", AIShellPolicy(max_actions=31))
    manager.advance("r")
    rolled = manager.rollback("r")
    assert rolled.phase is AIPolicyRolloutPhase.ROLLED_BACK
    assert store.current().policy == base


def test_complete_rollout_cannot_rollback():
    store = AIPolicyStore()
    manager = AIPolicyRolloutManager(store)
    manager.prepare("r", AIShellPolicy(max_actions=31))
    manager.advance("r")
    manager.advance("r")
    manager.advance("r")
    with pytest.raises(RuntimeError):
        manager.rollback("r")


def test_governance_quarantine_checks_all_dimensions():
    governance = AIShellGovernance()
    governance.quarantine.quarantine(
        QuarantineTarget.PROPOSAL,
        "p" * 64,
        reason="bad",
        actor="operator",
    )
    with pytest.raises(RuntimeError):
        governance.require_not_quarantined(
            model_id="m",
            proposal_fingerprint="p" * 64,
            commands=("python",),
        )


def test_governance_snapshot():
    governance = AIShellGovernance()
    snapshot = governance.snapshot()
    assert snapshot.policy_revision == 1
    assert len(snapshot.policy_fingerprint) == 64


def test_policy_rollout_prepared_does_not_activate_target():
    base = AIShellPolicy(max_actions=32)
    target = AIShellPolicy(max_actions=31)
    store = AIPolicyStore(base)
    manager = AIPolicyRolloutManager(store)
    rollout = manager.prepare("staged", target, canary_percent=100)
    assert rollout.phase is AIPolicyRolloutPhase.PREPARED
    assert rollout.target_revision == 0
    assert store.current().policy == base
    assert manager.policy_for("staged", "alice") == base


def test_policy_rollout_canary_resolves_target_without_global_flip():
    base = AIShellPolicy(max_actions=32)
    target = AIShellPolicy(max_actions=31)
    store = AIPolicyStore(base)
    manager = AIPolicyRolloutManager(store)
    manager.prepare("staged", target, canary_percent=100)
    manager.advance("staged")
    assert store.current().policy == base
    assert manager.policy_for("staged", "alice") == target


def test_policy_rollout_broad_activates_target_once():
    base = AIShellPolicy(max_actions=32)
    target = AIShellPolicy(max_actions=31)
    store = AIPolicyStore(base)
    manager = AIPolicyRolloutManager(store)
    manager.prepare("staged", target, canary_percent=100)
    manager.advance("staged")
    broad = manager.advance("staged")
    assert broad.phase is AIPolicyRolloutPhase.BROAD
    assert broad.target_revision == 2
    assert store.current().policy == target
    assert manager.policy_for("staged", "bob") == target


def test_policy_rollout_detects_concurrent_policy_change_before_broad():
    store = AIPolicyStore(AIShellPolicy(max_actions=32))
    manager = AIPolicyRolloutManager(store)
    manager.prepare("staged", AIShellPolicy(max_actions=31))
    manager.advance("staged")
    store.replace(AIShellPolicy(max_actions=30))
    with pytest.raises(RuntimeError, match="changed while rollout"):
        manager.advance("staged")
