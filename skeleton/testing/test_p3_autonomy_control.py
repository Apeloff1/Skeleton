from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from skeleton.ai.runtime.autonomous_engineering.autonomy import (
    AutonomyGrant,
    AutonomyLevel,
    AutonomyState,
    authorize_change_plan,
    deescalate,
    escalate,
    revoke,
)
from skeleton.ai.runtime.autonomous_engineering.safe_change import plan_safe_change
from skeleton.ai.runtime.autonomous_engineering.workflow import WorkflowCompiler
from skeleton.repo_machine.model import FileRecord, RepositoryModel, SubsystemRecord


NOW = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)


def _model() -> RepositoryModel:
    return RepositoryModel(
        schema_version=1,
        repository="fixture",
        files=(
            FileRecord(
                path="skeleton/core.py",
                zone="skeleton",
                owner="core",
                kind="source",
                language="python",
                size=10,
                lines=1,
                sha256=hashlib.sha256(b"core").hexdigest(),
            ),
        ),
        subsystems=(
            SubsystemRecord(
                name="skeleton",
                owner="core",
                criticality="critical",
                file_count=1,
                code_files=1,
                test_files=0,
                workflow_files=0,
                total_lines=1,
                total_bytes=10,
            ),
        ),
        edges=(),
        findings=(),
    )


def _plan():
    workflow = WorkflowCompiler().compile(
        {
            "workflow_id": "p3.autonomy",
            "version": "v1",
            "tasks": [
                {
                    "task_id": "edit",
                    "kind": "code",
                    "objective": "Apply a governed edit.",
                    "effect_class": "write",
                    "approval_required": True,
                    "required_capabilities": ["repo.write"],
                }
            ],
        }
    )
    return plan_safe_change(
        workflow,
        _model(),
        task_id="edit",
        changed_paths=["skeleton/core.py"],
        author_id="agent",
        reviewer_candidates=["reviewer"],
        verifier_candidates=["verifier"],
    )


def _grant(**overrides):
    values = {
        "grant_id": "grant-1",
        "actor_id": "agent",
        "max_level": AutonomyLevel.WRITE,
        "capabilities": ("repo.write",),
        "max_actions": 2,
        "max_risk_score": 70,
        "issued_at": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(hours=1),
        "evidence_refs": ("approval:grant-1",),
    }
    values.update(overrides)
    return AutonomyGrant(**values)


def test_write_requires_evidence_bound_escalation() -> None:
    state = AutonomyState("agent")
    decision, unchanged = authorize_change_plan(
        _grant(),
        state,
        _plan(),
        now=NOW,
    )
    assert decision.permitted is False
    assert decision.reason_code == "insufficient_autonomy_level"
    assert unchanged == state

    state = escalate(
        _grant(),
        state,
        target_level=AutonomyLevel.WRITE,
        evidence_refs=("evidence:risk-reviewed",),
        operator_approval_ref="approval:write",
    )
    assert state.level is AutonomyLevel.WRITE
    assert state.last_receipt_digest is not None

    decision, after = authorize_change_plan(
        _grant(),
        state,
        _plan(),
        now=NOW,
        evidence_refs=("evidence:safe-change-plan",),
    )
    assert decision.permitted is True
    assert after.actions_used == 1
    assert after.revision == state.revision + 1


def test_escalation_cannot_exceed_grant() -> None:
    grant = _grant(max_level=AutonomyLevel.READ)
    with pytest.raises(PermissionError, match="exceeds grant"):
        escalate(
            grant,
            AutonomyState("agent"),
            target_level=AutonomyLevel.WRITE,
            evidence_refs=("evidence:x",),
            operator_approval_ref="approval:x",
        )


def test_action_budget_is_consumed_only_on_success() -> None:
    grant = _grant(max_actions=1)
    state = escalate(
        grant,
        AutonomyState("agent"),
        target_level=AutonomyLevel.WRITE,
        evidence_refs=("evidence:x",),
        operator_approval_ref="approval:x",
    )
    first, state = authorize_change_plan(grant, state, _plan(), now=NOW)
    second, same = authorize_change_plan(grant, state, _plan(), now=NOW)
    assert first.permitted is True
    assert second.permitted is False
    assert second.reason_code == "action_budget_exhausted"
    assert same == state


def test_expired_grant_fails_closed() -> None:
    grant = _grant(expires_at=NOW)
    state = AutonomyState("agent", level=AutonomyLevel.WRITE)
    decision, same = authorize_change_plan(grant, state, _plan(), now=NOW)
    assert decision.reason_code == "grant_expired"
    assert same == state


def test_risk_budget_fails_closed() -> None:
    plan = _plan()
    grant = _grant(max_risk_score=max(0, plan.risk_score - 1))
    state = AutonomyState("agent", level=AutonomyLevel.WRITE)
    decision, _ = authorize_change_plan(grant, state, plan, now=NOW)
    assert decision.reason_code == "risk_budget_exceeded"


def test_deescalation_and_revocation_are_monotonic_controls() -> None:
    grant = _grant()
    state = AutonomyState("agent", level=AutonomyLevel.WRITE)
    state = deescalate(
        grant,
        state,
        target_level=AutonomyLevel.READ,
        evidence_refs=("evidence:cooldown",),
    )
    assert state.level is AutonomyLevel.READ
    state = revoke(grant, state, evidence_refs=("evidence:operator-stop",))
    assert state.level is AutonomyLevel.OBSERVE
    assert state.revoked is True
    with pytest.raises(PermissionError, match="revoked"):
        escalate(
            grant,
            state,
            target_level=AutonomyLevel.READ,
            evidence_refs=("evidence:no",),
        )
