from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.agents.autonomy_control import AutonomyLevel, AutonomyState
from skeleton.agents.blast_radius import (
    ActionRiskProfile,
    AdversarialAlignmentReport,
    BlastRadiusError,
    BlastRadiusPolicy,
    ImpactClass,
    ReversibilityClass,
    classify_impact,
    qualify_blast_radius,
)
from skeleton.agents.delegation_qualification import AgentDelegationDecision
from skeleton.agents.human_control import (
    HumanControlAction,
    HumanControlCommand,
    HumanControlState,
    evaluate_human_control,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.risk_evidence import RiskBindingEvaluation
from skeleton.contracts.safety_hazards import (
    DEFAULT_SAFETY_HAZARD_MANIFEST,
    DEFAULT_SAFETY_HAZARD_MANIFEST_DIGEST,
    DEFAULT_SAFETY_POLICY_ID,
    DEFAULT_SAFETY_POLICY_VERSION,
    SafetyHazardClass,
    SafetyHazardManifest,
)


NOW = 1_800_000_000.0


def _hazard_id(hazard_class: SafetyHazardClass) -> str:
    return next(
        item.hazard_id
        for item in DEFAULT_SAFETY_HAZARD_MANIFEST.hazards
        if item.hazard_class is hazard_class
    )


def _ref(
    source: str = "adversarial://independent-review",
    char: str = "1",
    *,
    category: str = "adversarial",
) -> EvidenceRef:
    return EvidenceRef(
        source=source,
        digest=char * 64,
        category=category,
    )


def _profile(**overrides: object) -> ActionRiskProfile:
    values: dict[str, object] = {
        "operation_id": "operation-1",
        "execution_id": "execution-1",
        "agent_id": "agent-1",
        "action_digest": "a" * 64,
        "authority_digest": "b" * 64,
        "affected_tenants": 1,
        "affected_resources": 3,
        "reversibility": ReversibilityClass.REVERSIBLE,
        "writes_persistent_state": False,
        "externally_observable": False,
        "privileged": False,
        "destructive": False,
        "sensitive_data": False,
    }
    values.update(overrides)
    return ActionRiskProfile(**values)


def _alignment(
    profile: ActionRiskProfile,
    **overrides: object,
) -> AdversarialAlignmentReport:
    values: dict[str, object] = {
        "operation_id": profile.operation_id,
        "execution_id": profile.execution_id,
        "agent_id": profile.agent_id,
        "action_digest": profile.action_digest,
        "authority_digest": profile.authority_digest,
        "verifier_id": "verifier:independent-1",
        "verifier_digest": "c" * 64,
        "independent": True,
        "goal_drift_detected": False,
        "specification_gaming_detected": False,
        "policy_conflict_detected": False,
        "deceptive_behavior_detected": False,
        "unresolved_counterexamples": 0,
        "evidence_refs": (_ref(),),
        "observed_at": NOW - 10.0,
        "expires_at": NOW + 300.0,
    }
    values.update(overrides)
    return AdversarialAlignmentReport(**values)


def _risk(
    *,
    severity: str = "high",
    resolved: bool = True,
    blockers: tuple[str, ...] = (),
) -> RiskBindingEvaluation:
    return RiskBindingEvaluation(
        obligation_id="P1-ADVERSARIAL-VOL-999-deadbeefdeadbeef",
        obligation_digest="d" * 64,
        resolved=resolved,
        blocking=True,
        severity=severity,
        disposition="evidence",
        blockers=blockers,
    )


def _human_approval(profile: ActionRiskProfile):
    delegation = AgentDelegationDecision(
        accepted=True,
        reasons=(),
        parent_authority_digest="1" * 64,
        child_authority_digest="2" * 64,
        handoff_digest="3" * 64,
        lease_fence_digest="4" * 64,
        live_lease_digest="5" * 64,
        observed_at=NOW - 30.0,
    )
    # For this focused downstream fixture the durable authority identity is the
    # exact digest bound into the proposed action.
    autonomy = AutonomyState(
        operation_id=profile.operation_id,
        execution_id=profile.execution_id,
        agent_id=profile.agent_id,
        level=AutonomyLevel.DELEGATED,
        delegation_digest=profile.authority_digest,
        version=4,
    )
    state = HumanControlState(
        operation_id=autonomy.operation_id,
        execution_id=autonomy.execution_id,
        agent_id=autonomy.agent_id,
        autonomy_state_digest=autonomy.digest,
        authority_digest=profile.authority_digest,
        level=autonomy.level,
        version=7,
    )
    command = HumanControlCommand(
        operation_id=state.operation_id,
        execution_id=state.execution_id,
        agent_id=state.agent_id,
        action=HumanControlAction.APPROVE,
        arguments_digest=profile.action_digest,
        authority_digest=state.authority_digest,
        state_digest=state.digest,
        state_version=state.version,
        issuer_id="human:operator-1",
        issuer_digest="e" * 64,
        issued_at=NOW - 20.0,
        expires_at=NOW + 300.0,
        evidence_refs=(
            _ref(
                "human://operator-1/approval",
                "6",
                category="human_control_authorization",
            ),
        ),
        requested_level=AutonomyLevel.AUTONOMOUS,
        independent=True,
    )
    decision = evaluate_human_control(
        state=state,
        command=command,
        autonomy_state=autonomy,
        observed_at=NOW,
    )
    assert decision.accepted is True
    return decision


def test_low_impact_exact_action_needs_no_human_or_risk_binding() -> None:
    profile = _profile()
    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
    )

    assert decision.accepted is True
    assert decision.impact is ImpactClass.LOW
    assert decision.risk_evaluation_digest is None
    assert decision.human_receipt_digest is None
    assert decision.safety_policy_id == DEFAULT_SAFETY_POLICY_ID
    assert decision.safety_policy_version == DEFAULT_SAFETY_POLICY_VERSION
    assert decision.hazard_manifest_digest == DEFAULT_SAFETY_HAZARD_MANIFEST_DIGEST
    assert decision.triggered_hazard_ids == ()
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "blast_radius_alignment_qualification"
    assert evidence.digest == decision.decision_digest


def test_moderate_persistent_action_can_qualify_with_independent_alignment() -> None:
    profile = _profile(writes_persistent_state=True)
    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
    )

    assert decision.accepted is True
    assert decision.impact is ImpactClass.MODERATE


def test_high_impact_requires_resolved_risk_and_exact_human_approval() -> None:
    profile = _profile(
        privileged=True,
        writes_persistent_state=True,
        externally_observable=True,
    )
    alignment = _alignment(profile)

    missing = qualify_blast_radius(
        profile=profile,
        alignment=alignment,
        observed_at=NOW,
    )
    assert missing.accepted is False
    assert missing.impact is ImpactClass.HIGH
    assert "human-approval-missing" in missing.reasons
    assert "risk-binding-missing" in missing.reasons
    assert _hazard_id(
        SafetyHazardClass.AUTHORITY_ESCALATION
    ) in missing.triggered_hazard_ids
    assert _hazard_id(
        SafetyHazardClass.IRREVERSIBLE_SIDE_EFFECT
    ) in missing.triggered_hazard_ids

    accepted = qualify_blast_radius(
        profile=profile,
        alignment=alignment,
        observed_at=NOW,
        risk_evaluation=_risk(severity="high"),
        human_approval=_human_approval(profile),
    )
    assert accepted.accepted is True
    assert accepted.risk_evaluation_digest is not None
    assert accepted.human_receipt_digest is not None
    assert accepted.safety_policy_id == DEFAULT_SAFETY_POLICY_ID
    assert accepted.safety_policy_version == DEFAULT_SAFETY_POLICY_VERSION
    assert accepted.hazard_manifest_digest == DEFAULT_SAFETY_HAZARD_MANIFEST_DIGEST
    assert _hazard_id(
        SafetyHazardClass.AUTHORITY_ESCALATION
    ) in accepted.triggered_hazard_ids
    assert _hazard_id(
        SafetyHazardClass.IRREVERSIBLE_SIDE_EFFECT
    ) in accepted.triggered_hazard_ids


def test_irreversible_action_is_critical_and_requires_critical_risk_binding() -> None:
    profile = _profile(
        reversibility=ReversibilityClass.IRREVERSIBLE,
        writes_persistent_state=True,
    )
    human = _human_approval(profile)

    wrong = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
        risk_evaluation=_risk(severity="high"),
        human_approval=human,
    )
    assert wrong.accepted is False
    assert wrong.impact is ImpactClass.CRITICAL
    assert "critical-risk-classification-mismatch" in wrong.reasons

    exact = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
        risk_evaluation=_risk(severity="critical"),
        human_approval=human,
    )
    assert exact.accepted is True


@pytest.mark.parametrize(
    ("alignment_overrides", "reason"),
    (
        ({"goal_drift_detected": True}, "goal-drift-detected"),
        (
            {"specification_gaming_detected": True},
            "specification-gaming-detected",
        ),
        ({"policy_conflict_detected": True}, "policy-conflict-detected"),
        ({"deceptive_behavior_detected": True}, "deceptive-behavior-detected"),
        ({"unresolved_counterexamples": 1}, "unresolved-counterexamples"),
        ({"independent": False}, "alignment-not-independent"),
        ({"verifier_id": "agent-1"}, "alignment-verifier-is-agent"),
        ({"expires_at": NOW}, "alignment-expired"),
        ({"observed_at": NOW + 1.0}, "alignment-not-yet-valid"),
        ({"action_digest": "9" * 64}, "alignment-action-mismatch"),
        ({"authority_digest": "8" * 64}, "alignment-authority-mismatch"),
        ({"operation_id": "other-operation"}, "alignment-operation-mismatch"),
        ({"execution_id": "other-execution"}, "alignment-execution-mismatch"),
        ({"agent_id": "other-agent"}, "alignment-agent-mismatch"),
    ),
)
def test_adversarial_alignment_failure_modes_block(
    alignment_overrides: dict,
    reason: str,
) -> None:
    profile = _profile()
    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile, **alignment_overrides),
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_high_impact_human_approval_must_bind_exact_action_and_authority() -> None:
    profile = _profile(privileged=True)
    human = _human_approval(profile)

    action_drift = replace(human, arguments_digest="7" * 64)
    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
        risk_evaluation=_risk(),
        human_approval=action_drift,
    )
    assert decision.accepted is False
    assert "human-approval-action-digest-mismatch" in decision.reasons

    authority_drift = replace(human, authority_digest="8" * 64)
    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
        risk_evaluation=_risk(),
        human_approval=authority_drift,
    )
    assert decision.accepted is False
    assert "human-approval-authority-mismatch" in decision.reasons


def test_high_impact_rejects_stale_rejected_or_wrong_action_approval() -> None:
    profile = _profile(privileged=True)
    human = _human_approval(profile)

    stale = replace(human, expires_at=NOW)
    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
        risk_evaluation=_risk(),
        human_approval=stale,
    )
    assert decision.accepted is False
    assert "human-approval-expired" in decision.reasons

    wrong_action = replace(human, action=HumanControlAction.OVERRIDE)
    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
        risk_evaluation=_risk(),
        human_approval=wrong_action,
    )
    assert decision.accepted is False
    assert "human-approval-action-mismatch" in decision.reasons

    rejected = replace(
        human,
        accepted=False,
        reasons=("forced-rejection",),
        next_version=human.current_version,
    )
    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
        risk_evaluation=_risk(),
        human_approval=rejected,
    )
    assert decision.accepted is False
    assert "human-approval-rejected" in decision.reasons


def test_unresolved_or_underclassified_risk_binding_blocks_high_impact() -> None:
    profile = _profile(privileged=True)
    human = _human_approval(profile)

    unresolved = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
        risk_evaluation=_risk(
            resolved=False,
            blockers=("binding review is overdue",),
        ),
        human_approval=human,
    )
    assert unresolved.accepted is False
    assert "risk-binding-unresolved" in unresolved.reasons

    low = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
        risk_evaluation=_risk(severity="medium"),
        human_approval=human,
    )
    assert low.accepted is False
    assert "high-risk-classification-mismatch" in low.reasons


def test_recoverable_profile_requires_recovery_and_rollback_evidence() -> None:
    with pytest.raises(BlastRadiusError, match="recovery_plan_digest"):
        _profile(
            reversibility=ReversibilityClass.RECOVERABLE,
            recovery_plan_digest=None,
            rollback_test_digest="1" * 64,
        )
    with pytest.raises(BlastRadiusError, match="rollback_test_digest"):
        _profile(
            reversibility=ReversibilityClass.RECOVERABLE,
            recovery_plan_digest="1" * 64,
            rollback_test_digest=None,
        )

    profile = _profile(
        reversibility=ReversibilityClass.RECOVERABLE,
        recovery_plan_digest="1" * 64,
        rollback_test_digest="2" * 64,
    )
    assert profile.reversibility is ReversibilityClass.RECOVERABLE


def test_impact_classification_is_deterministic_at_thresholds() -> None:
    policy = BlastRadiusPolicy(
        max_tenants_without_human=1,
        max_resources_without_human=25,
        critical_tenant_threshold=10,
        critical_resource_threshold=500,
    )

    assert classify_impact(_profile(), policy=policy) is ImpactClass.LOW
    assert (
        classify_impact(
            _profile(affected_resources=26),
            policy=policy,
        )
        is ImpactClass.HIGH
    )
    assert (
        classify_impact(
            _profile(affected_tenants=10),
            policy=policy,
        )
        is ImpactClass.CRITICAL
    )
    assert (
        classify_impact(
            _profile(affected_resources=500),
            policy=policy,
        )
        is ImpactClass.CRITICAL
    )


def test_rejected_decision_cannot_materialize_promotion_evidence() -> None:
    profile = _profile()
    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile, goal_drift_detected=True),
        observed_at=NOW,
    )

    assert decision.accepted is False
    with pytest.raises(BlastRadiusError, match="cannot become promotion"):
        decision.accepted_evidence_ref()


def test_alignment_evidence_order_is_canonical() -> None:
    profile = _profile()
    first = _ref("adversarial://a", "1")
    second = _ref("adversarial://b", "2")

    left = _alignment(
        profile,
        evidence_refs=(second, first, second),
    )
    right = _alignment(
        profile,
        evidence_refs=(first, second),
    )

    assert left.evidence_refs == right.evidence_refs
    assert left.digest == right.digest


def test_invalid_policy_and_profile_shapes_fail_closed() -> None:
    with pytest.raises(BlastRadiusError, match="critical_tenant_threshold"):
        BlastRadiusPolicy(
            max_tenants_without_human=2,
            critical_tenant_threshold=2,
        )
    with pytest.raises(BlastRadiusError, match="affected_tenants"):
        _profile(affected_tenants=0)
    with pytest.raises(BlastRadiusError, match="action_digest"):
        _profile(action_digest="not-a-digest")



def test_runtime_decision_binds_explicit_safety_policy_version() -> None:
    manifest = SafetyHazardManifest(
        policy_id=DEFAULT_SAFETY_POLICY_ID,
        policy_version=2,
        hazards=DEFAULT_SAFETY_HAZARD_MANIFEST.hazards,
    )
    policy = BlastRadiusPolicy(hazard_manifest=manifest)
    profile = _profile()

    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile),
        observed_at=NOW,
        policy=policy,
    )

    assert decision.accepted is True
    assert decision.safety_policy_id == DEFAULT_SAFETY_POLICY_ID
    assert decision.safety_policy_version == 2
    assert decision.hazard_manifest_digest == manifest.manifest_digest
    assert decision.policy_digest == policy.digest
    assert decision.policy_digest != BlastRadiusPolicy().digest


def test_goal_drift_binds_formal_goal_drift_hazard() -> None:
    profile = _profile()
    decision = qualify_blast_radius(
        profile=profile,
        alignment=_alignment(profile, goal_drift_detected=True),
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert _hazard_id(SafetyHazardClass.GOAL_DRIFT) in decision.triggered_hazard_ids


def test_blast_radius_source_and_ai_mirror_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/automation/agents/blast_radius.py"
    mirror = root / "skeleton/ai/agents/core/blast_radius.py"

    assert source.read_bytes() == mirror.read_bytes()
