from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.agents.autonomy_control import (
    AutonomyLevel,
    AutonomyTransitionDecision,
    TransitionDisposition,
)
from skeleton.agents.blast_radius import BlastRadiusDecision, ImpactClass
from skeleton.agents.delegation_qualification import AgentDelegationDecision
from skeleton.agents.human_control import (
    HumanControlAction,
    HumanControlDecision,
)
from skeleton.agents.safe_autonomy import (
    SafeAutonomyError,
    qualify_safe_autonomy,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.skills.privileged_transaction import PrivilegedToolTransactionDecision


NOW = 1_800_000_000.0


def _tool(**overrides: object) -> PrivilegedToolTransactionDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "manifest_digest": "1" * 64,
        "request_digest": "a" * 64,
        "receipt_digest": "2" * 64,
        "isolation_requirement_digest": "3" * 64,
        "isolation_observation_digest": "4" * 64,
        "receipt_persisted": True,
    }
    values.update(overrides)
    return PrivilegedToolTransactionDecision(**values)


def _delegation(**overrides: object) -> AgentDelegationDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "parent_authority_digest": "5" * 64,
        "child_authority_digest": "6" * 64,
        "handoff_digest": "7" * 64,
        "lease_fence_digest": "8" * 64,
        "live_lease_digest": "9" * 64,
        "observed_at": NOW - 30.0,
    }
    values.update(overrides)
    return AgentDelegationDecision(**values)


def _human(
    authority_digest: str,
    action_digest: str,
    **overrides: object,
) -> HumanControlDecision:
    values: dict[str, object] = {
        "accepted": True,
        "action": HumanControlAction.APPROVE,
        "reasons": (),
        "operation_id": "operation-1",
        "execution_id": "execution-1",
        "agent_id": "agent-1",
        "arguments_digest": action_digest,
        "state_digest": "b" * 64,
        "command_digest": "c" * 64,
        "autonomy_state_digest": "d" * 64,
        "authority_digest": authority_digest,
        "from_level": AutonomyLevel.DELEGATED,
        "requested_level": AutonomyLevel.AUTONOMOUS,
        "next_level": AutonomyLevel.DELEGATED,
        "next_paused": False,
        "next_interrupted": False,
        "current_version": 4,
        "next_version": 5,
        "issuer_id": "human:operator-1",
        "issuer_digest": "e" * 64,
        "expires_at": NOW + 300.0,
        "evidence_refs": (
            EvidenceRef(
                source="human://operator-1/approval",
                digest="f" * 64,
                category="human_control_authorization",
            ),
        ),
        "independent": True,
        "observed_at": NOW - 10.0,
        "previous_receipt_digest": None,
    }
    values.update(overrides)
    return HumanControlDecision(**values)


def _autonomy(
    delegation_digest: str,
    authorization_digest: str,
    **overrides: object,
) -> AutonomyTransitionDecision:
    values: dict[str, object] = {
        "accepted": True,
        "disposition": TransitionDisposition.APPLY,
        "from_level": AutonomyLevel.DELEGATED,
        "requested_level": AutonomyLevel.AUTONOMOUS,
        "next_level": AutonomyLevel.AUTONOMOUS,
        "reasons": (),
        "state_digest": "1" * 64,
        "signal_digest": "2" * 64,
        "policy_digest": "3" * 64,
        "delegation_digest": delegation_digest,
        "authorization_digest": authorization_digest,
    }
    values.update(overrides)
    return AutonomyTransitionDecision(**values)


def _blast(
    authority_digest: str,
    action_digest: str,
    human_receipt_digest: str,
    **overrides: object,
) -> BlastRadiusDecision:
    values: dict[str, object] = {
        "accepted": True,
        "impact": ImpactClass.HIGH,
        "reasons": (),
        "operation_id": "operation-1",
        "execution_id": "execution-1",
        "agent_id": "agent-1",
        "action_digest": action_digest,
        "authority_digest": authority_digest,
        "profile_digest": "4" * 64,
        "alignment_digest": "5" * 64,
        "policy_digest": "6" * 64,
        "risk_evaluation_digest": "7" * 64,
        "human_receipt_digest": human_receipt_digest,
    }
    values.update(overrides)
    return BlastRadiusDecision(**values)


def _chain():
    tool = _tool()
    delegation = _delegation()
    human = _human(delegation.decision_digest, tool.request_digest)
    authorization = human.accepted_autonomy_authorization()
    autonomy = _autonomy(delegation.decision_digest, authorization.digest)
    blast = _blast(
        delegation.decision_digest,
        tool.request_digest,
        human.receipt_digest,
    )
    return tool, delegation, autonomy, human, blast


def _qualify(
    *,
    tool=None,
    delegation=None,
    autonomy=None,
    human=None,
    blast=None,
    observed_at: float = NOW,
):
    defaults = _chain()
    return qualify_safe_autonomy(
        tool_transaction=defaults[0] if tool is None else tool,
        delegation=defaults[1] if delegation is None else delegation,
        autonomy_transition=defaults[2] if autonomy is None else autonomy,
        human_control=defaults[3] if human is None else human,
        blast_radius=defaults[4] if blast is None else blast,
        observed_at=observed_at,
    )


def test_accepts_exact_auto01_through_auto05_chain() -> None:
    tool, delegation, autonomy, human, blast = _chain()

    decision = qualify_safe_autonomy(
        tool_transaction=tool,
        delegation=delegation,
        autonomy_transition=autonomy,
        human_control=human,
        blast_radius=blast,
        observed_at=NOW,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.action_digest == tool.request_digest
    assert decision.authority_digest == delegation.decision_digest
    assert decision.human_control_receipt_digest == human.receipt_digest
    assert decision.blast_radius_digest == blast.decision_digest
    assert len(decision.chain_digest) == 64
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "safe_autonomy_qualification"
    assert evidence.digest == decision.decision_digest


def test_decision_identity_is_stable_across_observation_time() -> None:
    first = _qualify(observed_at=NOW)
    second = _qualify(observed_at=NOW + 1.0)

    assert first.accepted is True
    assert second.accepted is True
    assert first.observed_at != second.observed_at
    assert first.decision_digest == second.decision_digest
    assert first.chain_digest == second.chain_digest


@pytest.mark.parametrize("which", ("tool", "delegation", "autonomy", "human", "blast"))
def test_any_rejected_subdecision_blocks_terminal_bundle(which: str) -> None:
    tool, delegation, autonomy, human, blast = _chain()
    kwargs = {
        "tool": tool,
        "delegation": delegation,
        "autonomy": autonomy,
        "human": human,
        "blast": blast,
    }
    if which == "tool":
        kwargs["tool"] = replace(tool, accepted=False, reasons=("rejected",))
    elif which == "delegation":
        kwargs["delegation"] = replace(
            delegation,
            accepted=False,
            reasons=("rejected",),
        )
    elif which == "autonomy":
        kwargs["autonomy"] = replace(
            autonomy,
            accepted=False,
            reasons=("rejected",),
        )
    elif which == "human":
        kwargs["human"] = replace(
            human,
            accepted=False,
            reasons=("rejected",),
            next_version=human.current_version,
        )
    else:
        kwargs["blast"] = replace(
            blast,
            accepted=False,
            reasons=("rejected",),
        )

    decision = _qualify(**kwargs)
    assert decision.accepted is False
    assert any(reason.endswith("-rejected") for reason in decision.reasons)


def test_tool_receipt_must_be_persisted() -> None:
    tool, delegation, autonomy, human, blast = _chain()
    tool = replace(tool, receipt_persisted=False)

    decision = _qualify(
        tool=tool,
        delegation=delegation,
        autonomy=autonomy,
        human=human,
        blast=blast,
    )

    assert decision.accepted is False
    assert "tool-receipt-not-persisted" in decision.reasons


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("autonomy_authority", "autonomy-delegation-chain-mismatch"),
        ("human_authority", "human-authority-chain-mismatch"),
        ("blast_authority", "blast-authority-chain-mismatch"),
        ("human_action", "human-action-chain-mismatch"),
        ("blast_action", "blast-action-chain-mismatch"),
        ("operation", "operation-chain-mismatch"),
        ("execution", "execution-chain-mismatch"),
        ("agent", "agent-chain-mismatch"),
        ("human_receipt", "blast-human-receipt-mismatch"),
        ("authorization", "autonomy-authorization-chain-mismatch"),
    ),
)
def test_exact_chain_drift_fails_closed(mutation: str, reason: str) -> None:
    tool, delegation, autonomy, human, blast = _chain()

    if mutation == "autonomy_authority":
        autonomy = replace(autonomy, delegation_digest="0" * 64)
    elif mutation == "human_authority":
        human = replace(human, authority_digest="0" * 64)
    elif mutation == "blast_authority":
        blast = replace(blast, authority_digest="0" * 64)
    elif mutation == "human_action":
        human = replace(human, arguments_digest="0" * 64)
    elif mutation == "blast_action":
        blast = replace(blast, action_digest="0" * 64)
    elif mutation == "operation":
        blast = replace(blast, operation_id="other-operation")
    elif mutation == "execution":
        blast = replace(blast, execution_id="other-execution")
    elif mutation == "agent":
        blast = replace(blast, agent_id="other-agent")
    elif mutation == "human_receipt":
        blast = replace(blast, human_receipt_digest="0" * 64)
    else:
        autonomy = replace(autonomy, authorization_digest="0" * 64)

    decision = _qualify(
        tool=tool,
        delegation=delegation,
        autonomy=autonomy,
        human=human,
        blast=blast,
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_missing_blast_human_receipt_blocks() -> None:
    tool, delegation, autonomy, human, blast = _chain()
    blast = replace(blast, human_receipt_digest=None)

    decision = _qualify(
        tool=tool,
        delegation=delegation,
        autonomy=autonomy,
        human=human,
        blast=blast,
    )

    assert decision.accepted is False
    assert "blast-human-receipt-missing" in decision.reasons


def test_human_control_must_be_live_independent_approval() -> None:
    tool, delegation, autonomy, human, blast = _chain()

    stale = replace(human, expires_at=NOW)
    decision = _qualify(
        tool=tool,
        delegation=delegation,
        autonomy=autonomy,
        human=stale,
        blast=blast,
    )
    assert decision.accepted is False
    assert "human-control-expired" in decision.reasons

    wrong_action = replace(human, action=HumanControlAction.OVERRIDE)
    decision = _qualify(
        tool=tool,
        delegation=delegation,
        autonomy=autonomy,
        human=wrong_action,
        blast=blast,
    )
    assert decision.accepted is False
    assert "human-control-not-approval" in decision.reasons
    assert "human-authorization-unavailable" in decision.reasons


def test_future_dated_human_control_blocks() -> None:
    tool, delegation, autonomy, human, blast = _chain()
    human = replace(human, observed_at=NOW + 1.0)

    decision = _qualify(
        tool=tool,
        delegation=delegation,
        autonomy=autonomy,
        human=human,
        blast=blast,
    )

    assert decision.accepted is False
    assert "human-control-not-yet-valid" in decision.reasons


def test_missing_autonomy_authorization_blocks() -> None:
    tool, delegation, autonomy, human, blast = _chain()
    autonomy = replace(autonomy, authorization_digest=None)

    decision = _qualify(
        tool=tool,
        delegation=delegation,
        autonomy=autonomy,
        human=human,
        blast=blast,
    )

    assert decision.accepted is False
    assert "autonomy-authorization-missing" in decision.reasons


def test_rejected_bundle_cannot_materialize_promotion_evidence() -> None:
    tool, delegation, autonomy, human, blast = _chain()
    blast = replace(blast, action_digest="0" * 64)

    decision = _qualify(
        tool=tool,
        delegation=delegation,
        autonomy=autonomy,
        human=human,
        blast=blast,
    )

    assert decision.accepted is False
    with pytest.raises(SafeAutonomyError, match="cannot become promotion"):
        decision.accepted_evidence_ref()
