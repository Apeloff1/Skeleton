from __future__ import annotations

import hashlib
import sqlite3

import pytest

from skeleton.automation.agents.autonomy_control import AutonomyLevel
from skeleton.automation.agents.human_control import (
    HumanControlAction,
    HumanControlDecision,
)
from skeleton.automation.agents.long_horizon import (
    LongHorizonConflict,
    LongHorizonError,
    LongRunningState,
    PersistentLongHorizonScheduler,
    ReauthorizationRequired,
    SqliteLongHorizonStore,
)
from skeleton.contracts.canonical import EvidenceRef, canonical_json_bytes


NOW = 1_800_000_000.0


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


OBJECTIVE = _digest("objective:v1")
AUTHORITY = _digest("authority:v1")


def _decision(
    action: HumanControlAction,
    *,
    authority_digest: str = AUTHORITY,
    observed_at: float = NOW + 2.0,
    expires_at: float = NOW + 300.0,
    next_paused: bool = False,
    next_interrupted: bool = False,
    requested_level: AutonomyLevel | None = None,
) -> HumanControlDecision:
    return HumanControlDecision(
        accepted=True,
        action=action,
        reasons=(),
        operation_id="op-1",
        execution_id="exec-1",
        agent_id="agent-1",
        arguments_digest=_digest(f"args:{action.value}"),
        state_digest=_digest(f"human-state:{action.value}"),
        command_digest=_digest(f"human-command:{action.value}"),
        autonomy_state_digest=_digest("autonomy-state"),
        authority_digest=authority_digest,
        from_level=AutonomyLevel.DELEGATED,
        requested_level=requested_level,
        next_level=(
            requested_level
            if requested_level is not None
            else AutonomyLevel.DELEGATED
        ),
        next_paused=next_paused,
        next_interrupted=next_interrupted,
        current_version=1,
        next_version=2,
        issuer_id="operator-1",
        issuer_digest=_digest("operator-1"),
        expires_at=expires_at,
        evidence_refs=(
            EvidenceRef(
                source=f"test:human-control:{action.value}",
                digest=_digest(f"evidence:{action.value}"),
                category="human_control_qualification",
            ),
        ),
        independent=True,
        observed_at=observed_at,
        previous_receipt_digest=None,
    )


def _scheduler(
    tmp_path,
    *,
    max_attempts: int = 4,
    step_budget: int = 8,
    deadline_at: float = NOW + 3600.0,
) -> PersistentLongHorizonScheduler:
    store = SqliteLongHorizonStore(tmp_path / "long-horizon.sqlite3")
    scheduler = PersistentLongHorizonScheduler(store)
    scheduler.register(
        operation_id="op-1",
        execution_id="exec-1",
        agent_id="agent-1",
        objective_digest=OBJECTIVE,
        authority_digest=AUTHORITY,
        now=NOW,
        deadline_at=deadline_at,
        max_attempts=max_attempts,
        step_budget=step_budget,
    )
    return scheduler


def test_operation_checkpoint_wait_and_restart_are_durable(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)

    claimed = scheduler.claim_due(now=NOW, limit=1)
    assert len(claimed) == 1
    assert claimed[0].state is LongRunningState.RUNNING
    assert claimed[0].attempts == 1

    checkpoint = scheduler.checkpoint(
        "op-1",
        {"phase": "research", "cursor": 7},
        now=NOW + 1.0,
    )
    waiting = scheduler.wait_until(
        "op-1",
        until=NOW + 10.0,
        now=NOW + 2.0,
    )
    assert waiting.state is LongRunningState.WAITING
    assert waiting.checkpoint_sequence == checkpoint.sequence

    restarted_store = SqliteLongHorizonStore(tmp_path / "long-horizon.sqlite3")
    restarted = PersistentLongHorizonScheduler(restarted_store)

    persisted = restarted_store.get("op-1")
    assert persisted.state is LongRunningState.WAITING
    loaded_checkpoint, payload = restarted_store.load_checkpoint("op-1")
    assert loaded_checkpoint == checkpoint
    assert payload == {"phase": "research", "cursor": 7}

    assert restarted.claim_due(now=NOW + 9.0) == ()
    resumed = restarted.claim_due(now=NOW + 10.0)
    assert len(resumed) == 1
    assert resumed[0].state is LongRunningState.RUNNING
    assert resumed[0].attempts == 2


def test_retry_wait_survives_restart_and_clears_error_on_claim(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    retry = scheduler.retry_after(
        "op-1",
        delay_s=30.0,
        error="provider_temporarily_unavailable",
        now=NOW + 1.0,
    )
    assert retry.state is LongRunningState.RETRY_WAIT
    assert retry.error == "provider_temporarily_unavailable"

    restarted = PersistentLongHorizonScheduler(
        SqliteLongHorizonStore(tmp_path / "long-horizon.sqlite3")
    )
    assert restarted.claim_due(now=NOW + 30.0) == ()
    claimed = restarted.claim_due(now=NOW + 31.0)
    assert len(claimed) == 1
    assert claimed[0].error is None
    assert claimed[0].attempts == 2


def test_resume_token_is_one_shot_and_goal_bound(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    scheduler.checkpoint(
        "op-1",
        {"phase": "tool-loop", "step": 3},
        now=NOW + 1.0,
    )
    pause = scheduler.apply_human_control(
        _decision(
            HumanControlAction.PAUSE,
            next_paused=True,
            observed_at=NOW + 2.0,
        ),
        now=NOW + 2.0,
    )
    assert pause.next_state is LongRunningState.PAUSED

    token = scheduler.issue_resume_token(
        "op-1",
        now=NOW + 3.0,
        expires_at=NOW + 100.0,
    )
    resumed = scheduler.resume(
        token,
        now=NOW + 4.0,
        objective_digest=OBJECTIVE,
        authority_digest=AUTHORITY,
    )
    assert resumed.state is LongRunningState.QUEUED

    with pytest.raises(LongHorizonConflict, match="already consumed"):
        scheduler.resume(
            token,
            now=NOW + 5.0,
            objective_digest=OBJECTIVE,
            authority_digest=AUTHORITY,
        )


def test_resume_rejects_goal_or_authority_drift_before_consuming_token(
    tmp_path,
) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    scheduler.checkpoint("op-1", {"phase": "safe"}, now=NOW + 1.0)
    scheduler.apply_human_control(
        _decision(HumanControlAction.PAUSE, next_paused=True),
        now=NOW + 2.0,
    )
    token = scheduler.issue_resume_token(
        "op-1",
        now=NOW + 3.0,
        expires_at=NOW + 100.0,
    )

    with pytest.raises(ReauthorizationRequired):
        scheduler.resume(
            token,
            now=NOW + 4.0,
            objective_digest=_digest("objective:drifted"),
            authority_digest=AUTHORITY,
        )

    resumed = scheduler.resume(
        token,
        now=NOW + 5.0,
        objective_digest=OBJECTIVE,
        authority_digest=AUTHORITY,
    )
    assert resumed.state is LongRunningState.QUEUED


def test_checkpoint_after_token_issue_makes_token_stale(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    scheduler.checkpoint("op-1", {"version": 1}, now=NOW + 1.0)
    scheduler.apply_human_control(
        _decision(HumanControlAction.PAUSE, next_paused=True),
        now=NOW + 2.0,
    )
    token = scheduler.issue_resume_token(
        "op-1",
        now=NOW + 3.0,
        expires_at=NOW + 100.0,
    )
    scheduler.checkpoint("op-1", {"version": 2}, now=NOW + 4.0)

    with pytest.raises(LongHorizonConflict, match="version is stale"):
        scheduler.resume(
            token,
            now=NOW + 5.0,
            objective_digest=OBJECTIVE,
            authority_digest=AUTHORITY,
        )


def test_human_pause_resume_and_interrupt_share_one_control_api(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)

    pause = scheduler.apply_human_control(
        _decision(HumanControlAction.PAUSE, next_paused=True),
        now=NOW + 2.0,
    )
    assert pause.previous_state is LongRunningState.RUNNING
    assert pause.next_state is LongRunningState.PAUSED
    assert scheduler.store.get("op-1").state is LongRunningState.PAUSED

    resume = scheduler.apply_human_control(
        _decision(
            HumanControlAction.RESUME,
            observed_at=NOW + 3.0,
            expires_at=NOW + 300.0,
        ),
        now=NOW + 3.0,
    )
    assert resume.next_state is LongRunningState.QUEUED

    scheduler.claim_due(now=NOW + 4.0)
    interrupt = scheduler.apply_human_control(
        _decision(
            HumanControlAction.INTERRUPT,
            observed_at=NOW + 5.0,
            expires_at=NOW + 300.0,
            next_interrupted=True,
        ),
        now=NOW + 5.0,
    )
    assert interrupt.next_state is LongRunningState.INTERRUPTED
    assert scheduler.store.get("op-1").terminal is True
    assert scheduler.claim_due(now=NOW + 6.0) == ()


def test_expired_human_control_receipt_cannot_mutate_operation(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)

    expired = _decision(
        HumanControlAction.PAUSE,
        observed_at=NOW + 1.0,
        expires_at=NOW + 2.0,
        next_paused=True,
    )
    with pytest.raises(LongHorizonConflict, match="expired"):
        scheduler.apply_human_control(expired, now=NOW + 3.0)

    assert scheduler.store.get("op-1").state is LongRunningState.RUNNING


def test_goal_reauthorization_requires_accepted_human_override(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    new_objective = _digest("objective:v2")
    new_authority = _digest("authority:v2")

    pause = _decision(
        HumanControlAction.PAUSE,
        next_paused=True,
        observed_at=NOW + 1.0,
    )
    with pytest.raises(ReauthorizationRequired, match="accepted human override"):
        scheduler.reauthorize_goal(
            "op-1",
            objective_digest=new_objective,
            authority_digest=new_authority,
            decision=pause,
            now=NOW + 2.0,
        )

    override = _decision(
        HumanControlAction.OVERRIDE,
        requested_level=AutonomyLevel.DELEGATED,
        observed_at=NOW + 2.0,
    )
    rebound = scheduler.reauthorize_goal(
        "op-1",
        objective_digest=new_objective,
        authority_digest=new_authority,
        decision=override,
        now=NOW + 2.0,
    )
    assert rebound.objective_digest == new_objective
    assert rebound.authority_digest == new_authority
    assert rebound.state is LongRunningState.QUEUED

    with pytest.raises(ReauthorizationRequired):
        scheduler.store.assert_goal(
            "op-1",
            objective_digest=OBJECTIVE,
            authority_digest=AUTHORITY,
        )
    assert scheduler.store.assert_goal(
        "op-1",
        objective_digest=new_objective,
        authority_digest=new_authority,
    ) == rebound


def test_deadline_expiry_is_enforced_before_claim(tmp_path) -> None:
    scheduler = _scheduler(tmp_path, deadline_at=NOW + 5.0)

    assert scheduler.claim_due(now=NOW + 5.0) == ()
    expired = scheduler.store.get("op-1")
    assert expired.state is LongRunningState.EXPIRED
    assert expired.error == "deadline_exceeded"


def test_step_budget_exhaustion_fails_before_next_claim(tmp_path) -> None:
    scheduler = _scheduler(tmp_path, step_budget=1)
    scheduler.claim_due(now=NOW)
    waiting = scheduler.wait_until(
        "op-1",
        until=NOW + 3.0,
        now=NOW + 1.0,
        step_increment=1,
    )
    assert waiting.steps_used == 1

    assert scheduler.claim_due(now=NOW + 3.0) == ()
    failed = scheduler.store.get("op-1")
    assert failed.state is LongRunningState.FAILED
    assert failed.error == "step_budget_exhausted"


def test_attempt_budget_exhaustion_fails_before_retry_claim(tmp_path) -> None:
    scheduler = _scheduler(tmp_path, max_attempts=1)
    scheduler.claim_due(now=NOW)
    scheduler.retry_after(
        "op-1",
        delay_s=1.0,
        error="transient",
        now=NOW + 1.0,
        step_increment=0,
    )

    assert scheduler.claim_due(now=NOW + 2.0) == ()
    failed = scheduler.store.get("op-1")
    assert failed.state is LongRunningState.FAILED
    assert failed.error == "attempt_budget_exhausted"


def test_checkpoint_digest_tampering_is_detected(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    checkpoint = scheduler.checkpoint(
        "op-1",
        {"phase": "verified", "cursor": 4},
        now=NOW + 1.0,
    )

    with sqlite3.connect(tmp_path / "long-horizon.sqlite3") as conn:
        conn.execute(
            """
            UPDATE long_horizon_checkpoint
            SET payload_json = ?
            WHERE operation_id = ? AND sequence = ?
            """,
            ('{"phase":"tampered","cursor":999}', "op-1", checkpoint.sequence),
        )

    with pytest.raises(LongHorizonError, match="digest mismatch"):
        scheduler.store.load_checkpoint("op-1", checkpoint.sequence)


def test_checkpoint_digest_uses_shared_canonical_contract_bytes(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    payload = {"phase": "verified", "cursor": 4, "nested": {"ok": True}}

    checkpoint = scheduler.checkpoint("op-1", payload, now=NOW + 1.0)

    expected = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    assert checkpoint.payload_digest == expected


def test_checkpoint_rejects_non_string_mapping_keys(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)

    with pytest.raises(LongHorizonError, match="checkpoint payload must be canonical JSON"):
        scheduler.checkpoint("op-1", {1: "not-canonical"}, now=NOW + 1.0)


def test_cancel_is_idempotent_for_terminal_operation(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    cancelled = scheduler.cancel("op-1", now=NOW + 1.0)
    assert cancelled.state is LongRunningState.CANCELLED
    assert scheduler.cancel("op-1", now=NOW + 2.0) == cancelled


def test_source_and_ai_long_horizon_mirror_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/automation/agents/long_horizon.py"
    mirror = root / "skeleton/ai/agents/core/long_horizon.py"

    assert source.read_bytes() == mirror.read_bytes()


def test_restart_does_not_reclaim_paused_operation_without_control_receipt(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    scheduler.apply_human_control(
        _decision(HumanControlAction.PAUSE, next_paused=True),
        now=NOW + 2.0,
    )

    restarted = PersistentLongHorizonScheduler(
        SqliteLongHorizonStore(tmp_path / "long-horizon.sqlite3")
    )
    assert restarted.claim_due(now=NOW + 100.0) == ()
    assert restarted.store.get("op-1").state is LongRunningState.PAUSED


def test_restart_preserves_terminal_interrupt_and_never_requeues(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    scheduler.apply_human_control(
        _decision(
            HumanControlAction.INTERRUPT,
            observed_at=NOW + 2.0,
            next_interrupted=True,
        ),
        now=NOW + 2.0,
    )

    restarted = PersistentLongHorizonScheduler(
        SqliteLongHorizonStore(tmp_path / "long-horizon.sqlite3")
    )
    assert restarted.claim_due(now=NOW + 100.0) == ()
    persisted = restarted.store.get("op-1")
    assert persisted.state is LongRunningState.INTERRUPTED
    assert persisted.terminal is True


def test_tampered_checkpoint_remains_rejected_after_process_restart(tmp_path) -> None:
    scheduler = _scheduler(tmp_path)
    scheduler.claim_due(now=NOW)
    checkpoint = scheduler.checkpoint(
        "op-1",
        {"phase": "durable", "cursor": 9},
        now=NOW + 1.0,
    )
    with sqlite3.connect(tmp_path / "long-horizon.sqlite3") as conn:
        conn.execute(
            "UPDATE long_horizon_checkpoint SET payload_json = ? "
            "WHERE operation_id = ? AND sequence = ?",
            ('{"phase":"forged","cursor":9}', "op-1", checkpoint.sequence),
        )

    restarted = PersistentLongHorizonScheduler(
        SqliteLongHorizonStore(tmp_path / "long-horizon.sqlite3")
    )
    with pytest.raises(LongHorizonError, match="digest mismatch"):
        restarted.store.load_checkpoint("op-1", checkpoint.sequence)
