from __future__ import annotations

from decimal import Decimal
import hashlib

import pytest

from skeleton.ai.runtime.autonomous_engineering.coordination import (
    AgentSeat,
    CoordinationError,
    EvidencePosition,
    HandoffPacket,
    build_coordination_plan,
    decide_disagreement,
    delegate,
    record_performance,
)


def _seat(agent_id, *, caps=("repo.read", "repo.write"), scopes=("repo",), mutations=(), cost="10"):
    return AgentSeat(
        agent_id=agent_id,
        role="engineer",
        capabilities=caps,
        authority_scopes=scopes,
        mutation_scopes=mutations,
        max_cost=Decimal(cost),
    )


def test_delegation_is_strict_authority_subset() -> None:
    sender = _seat("supervisor", scopes=("repo", "tests"))
    receiver = _seat("worker", scopes=("repo",))
    packet = HandoffPacket(
        handoff_id="handoff-1",
        task_id="task-1",
        sender_id="supervisor",
        receiver_id="worker",
        delegated_capabilities=("repo.write",),
        delegated_authority_scopes=("repo",),
        conflict_domains=("repo",),
        evidence_refs=("evidence:scope",),
        max_cost=Decimal("2"),
    )
    receipt = delegate(packet, sender=sender, receiver=receiver)
    assert receipt.permitted is True

    amplified = HandoffPacket(
        handoff_id="handoff-2",
        task_id="task-1",
        sender_id="supervisor",
        receiver_id="worker",
        delegated_capabilities=("repo.write",),
        delegated_authority_scopes=("tests",),
        conflict_domains=("repo",),
        evidence_refs=("evidence:scope",),
        max_cost=Decimal("2"),
    )
    denied = delegate(amplified, sender=sender, receiver=receiver)
    assert denied.permitted is False
    assert denied.reason_code == "receiver_authority_missing"


def test_coordination_detects_overlapping_mutation_domains() -> None:
    plan = build_coordination_plan(
        (
            _seat("a", mutations=("skeleton",)),
            _seat("b", mutations=("skeleton/core.py",)),
        ),
        (),
    )
    assert plan.executable is False
    assert plan.conflict_pairs == (("a", "b", "skeleton"),)


def test_coordination_is_executable_when_scopes_do_not_overlap() -> None:
    sender = _seat("supervisor", mutations=("docs",))
    worker = _seat("worker", mutations=("skeleton",))
    packet = HandoffPacket(
        handoff_id="handoff-1",
        task_id="task-1",
        sender_id="supervisor",
        receiver_id="worker",
        delegated_capabilities=("repo.write",),
        delegated_authority_scopes=("repo",),
        conflict_domains=("skeleton",),
        evidence_refs=("evidence:handoff",),
        max_cost=Decimal("1"),
    )
    plan = build_coordination_plan((sender, worker), (packet,))
    assert plan.executable is True
    assert plan.delegation_receipts[0].permitted is True


def test_performance_keeps_dimensions_and_identity_separate() -> None:
    digest = hashlib.sha256(b"x").hexdigest()
    record = record_performance(
        agent_id="worker",
        task_id="task-1",
        config_digest=digest,
        model_digest=digest,
        completion="1",
        correctness="0.9",
        recovery="0.5",
        cost="1.25",
        human_interventions=2,
        delegation_cost="0.25",
        evidence_refs=("eval:1",),
    )
    assert record.completion == Decimal("1.000000")
    assert record.correctness == Decimal("0.900000")
    assert record.recovery == Decimal("0.500000")
    assert record.cost == Decimal("1.250000")
    assert record.human_interventions == 2


def test_high_impact_disagreement_escalates_instead_of_averaging() -> None:
    decision = decide_disagreement(
        (
            EvidencePosition("agent-a", "safe", ("evidence:a",), Decimal("0.9")),
            EvidencePosition("agent-b", "unsafe", ("evidence:b",), Decimal("0.9")),
            EvidencePosition("agent-c", "safe", ("evidence:c",), Decimal("0.7")),
        ),
        impact="critical",
        consensus_threshold=Decimal("0.8"),
    )
    assert decision.status == "escalated"
    assert decision.selected_position is None
    assert decision.escalation_required is True
    assert {item.agent_id for item in decision.preserved_positions} == {
        "agent-a",
        "agent-b",
        "agent-c",
    }


def test_low_impact_can_resolve_while_preserving_dissent() -> None:
    decision = decide_disagreement(
        (
            EvidencePosition("agent-a", "option-a", ("e:a",), Decimal("0.8")),
            EvidencePosition("agent-b", "option-b", ("e:b",), Decimal("0.7")),
        ),
        impact="low",
    )
    assert decision.status == "resolved"
    assert decision.selected_position == "option-a"
    assert len(decision.preserved_positions) == 2


def test_duplicate_agent_positions_are_rejected() -> None:
    with pytest.raises(CoordinationError, match="independent"):
        decide_disagreement(
            (
                EvidencePosition("agent-a", "a", ("e:1",), Decimal("0.5")),
                EvidencePosition("agent-a", "b", ("e:2",), Decimal("0.5")),
            ),
            impact="high",
        )
