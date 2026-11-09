from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.cognitive_control_plane import (
    ControlPlanePolicy,
    ControlReadiness,
)
from skeleton.jeeves.agent.frontier_control_plane import FrontierCognitiveControlPlane
from skeleton.jeeves.agent.live_supervisor import (
    BeliefParticle,
    BeliefStateSummary,
    Intervention,
    InterventionKind,
    SupervisorSignals,
)
from skeleton.jeeves.agent.types import AgentPhase, Budget, RiskTier, Usage, stable_id


class StubSupervisor:
    def __init__(self, kinds):
        self.kinds = list(kinds)
        self.index = 0

    def evaluate(self, signals: SupervisorSignals) -> Intervention:
        kind = self.kinds[self.index % len(self.kinds)]
        self.index += 1
        hard = kind in {
            InterventionKind.ABORT_RUN,
            InterventionKind.REQUEST_CONFIRMATION,
            InterventionKind.ABORT_OPTION,
        }
        return Intervention(
            intervention_id=stable_id(
                "stub-intervention",
                {"run": signals.run_id, "kind": kind.value, "index": self.index},
            ),
            run_id=signals.run_id,
            kind=kind,
            reason=f"stub {kind.value}",
            priority=0.9 if hard else 0.4,
            created_at=float(self.index),
            directive=f"do {kind.value}",
            hard=hard,
        )


def _belief(*, uncertainty: float = 0.2, contradiction: float = 0.0) -> BeliefStateSummary:
    maximum = 1.0 - uncertainty
    particle = BeliefParticle("state-a", maximum)
    unknown = max(0.0, 1.0 - maximum)
    return BeliefStateSummary(
        particles=(particle,),
        entropy_bits=0.5,
        maximum_probability=maximum,
        effective_states=1.4,
        unknown_mass=unknown,
        contradiction_pressure=contradiction,
        information_gain_candidates=(),
    )


def _signals(
    run_id: str,
    *,
    progress: float,
    failures: int = 0,
    verification_failures: int = 0,
    ready: int = 1,
    failed: int = 0,
    blocked: int = 0,
    uncertainty: float = 0.2,
    contradiction: float = 0.0,
    stale: int = 0,
    evidence_growth: int = 1,
    loop: float = 0.0,
    pending_confirmation: bool = False,
    risk: RiskTier = RiskTier.READ_ONLY,
    usage_steps: int = 2,
) -> SupervisorSignals:
    return SupervisorSignals(
        run_id=run_id,
        phase=AgentPhase.EXECUTING,
        usage=Usage(steps=usage_steps),
        budget=Budget(
            max_steps=100,
            max_model_calls=100,
            max_tool_calls=100,
            max_tokens=1_000_000,
            max_wall_seconds=10_000,
        ),
        progress=progress,
        failure_streak=failures,
        verification_failure_streak=verification_failures,
        replans=0,
        pending_confirmation=pending_confirmation,
        current_risk=risk,
        plan_ready_steps=ready,
        plan_failed_steps=failed,
        plan_blocked_steps=blocked,
        belief=_belief(uncertainty=uncertainty, contradiction=contradiction),
        evidence_growth=evidence_growth,
        stale_cycles=stale,
        loop_severity=loop,
    )


def _policy() -> ControlPlanePolicy:
    base = ControlPlanePolicy()
    return replace(
        base,
        minimum_verified_transitions=12,
        minimum_action_support=2,
        learn_every=6,
        ensemble_minimum_models=2,
        ensemble_maximum_models=5,
        minimum_promoted_targets=2,
        minimum_override_gain=0.0,
        history_limit=1000,
        mechanism_policy=replace(
            base.mechanism_policy,
            minimum_train_samples=6,
            minimum_effective_sample_size=5.0,
            minimum_interventional_parent_samples=2,
            minimum_confidence=0.10,
            maximum_log_loss=10.0,
            maximum_brier_score=1.0,
            maximum_ece=1.0,
        ),
    )


def test_hard_abort_is_never_overridden() -> None:
    plane = FrontierCognitiveControlPlane(
        StubSupervisor([InterventionKind.ABORT_RUN]),
        policy=_policy(),
        clock=lambda: 100.0,
    )
    result = plane.evaluate(_signals("run-hard", progress=0.2))
    assert result.kind is InterventionKind.ABORT_RUN
    assert result.hard
    decision = plane.decisions(run_id="run-hard")[-1]
    assert decision.selected.kind is InterventionKind.ABORT_RUN
    assert decision.safety.hard_baseline_preserved


def test_confirmation_gate_is_never_weakened() -> None:
    plane = FrontierCognitiveControlPlane(
        StubSupervisor([InterventionKind.REQUEST_CONFIRMATION]),
        policy=_policy(),
        clock=lambda: 100.0,
    )
    result = plane.evaluate(
        _signals("run-confirm", progress=0.3, pending_confirmation=True)
    )
    assert result.kind is InterventionKind.REQUEST_CONFIRMATION
    decision = plane.decisions(run_id="run-confirm")[-1]
    assert decision.safety.confirmation_preserved


def test_cold_control_plane_retains_soft_baseline() -> None:
    plane = FrontierCognitiveControlPlane(
        StubSupervisor([InterventionKind.CONTINUE]),
        policy=_policy(),
        clock=lambda: 100.0,
    )
    result = plane.evaluate(_signals("cold", progress=0.1))
    assert result.kind is InterventionKind.CONTINUE
    assert plane.readiness is ControlReadiness.COLD
    assert "cold" in " ".join(plane.decisions(run_id="cold")[-1].reasons)


def _feed_transition(
    plane: FrontierCognitiveControlPlane,
    index: int,
    *,
    before_progress: float,
    after_progress: float,
    failures_after: int = 0,
    uncertainty_before: float = 0.4,
    uncertainty_after: float = 0.2,
) -> None:
    run_id = f"learn-{index}"
    plane.evaluate(
        _signals(
            run_id,
            progress=before_progress,
            uncertainty=uncertainty_before,
            evidence_growth=0,
            stale=1,
        )
    )
    record = plane.observe_next(
        _signals(
            run_id,
            progress=after_progress,
            failures=failures_after,
            uncertainty=uncertainty_after,
            evidence_growth=1,
            stale=0,
        ),
        verified=True,
    )
    assert record is not None
    assert record.verified


def test_verified_transitions_drive_learning_cycles_and_model_snapshots() -> None:
    supervisor = StubSupervisor(
        [
            InterventionKind.CONTINUE,
            InterventionKind.SEEK_INFORMATION,
            InterventionKind.VERIFY,
        ]
    )
    plane = FrontierCognitiveControlPlane(
        supervisor,
        policy=_policy(),
        clock=lambda: 100.0,
    )
    for index in range(1, 25):
        _feed_transition(
            plane,
            index,
            before_progress=min(0.70, index / 40),
            after_progress=min(0.95, index / 40 + 0.06),
        )
    assert len(plane.transitions(verified_only=True)) == 24
    assert plane.cycles()
    assert any(cycle.reports for cycle in plane.cycles())
    # Multiple learning cuts should create frozen model revisions if promotion
    # succeeds; if a target is rejected, the cycle records that explicitly.
    assert all(cycle.promoted_targets or cycle.rejected_targets for cycle in plane.cycles())
    summary = plane.summary()
    assert summary["inference"]["backend"] == "sparse-variable-elimination"


def test_unverified_transitions_do_not_increment_action_support() -> None:
    plane = FrontierCognitiveControlPlane(
        StubSupervisor([InterventionKind.CONTINUE]),
        policy=_policy(),
        clock=lambda: 100.0,
    )
    plane.evaluate(_signals("unverified", progress=0.1))
    record = plane.observe_next(
        _signals("unverified", progress=0.9),
        verified=False,
    )
    assert record is not None and not record.verified
    assert plane.summary()["action_support"].get("continue", 0) == 0


def test_control_transition_keeps_do_action_separate_from_state_observation() -> None:
    plane = FrontierCognitiveControlPlane(
        StubSupervisor([InterventionKind.VERIFY]),
        policy=_policy(),
        clock=lambda: 100.0,
    )
    plane.evaluate(_signals("intervention-semantics", progress=0.2))
    plane.observe_next(
        _signals("intervention-semantics", progress=0.3),
        verified=True,
    )
    sample = plane._samples[-1]
    assert sample.interventions == {"control_action": "verify"}
    assert "control_action" not in sample.before
    assert sample.verified


def test_safety_audit_rejects_risk_increasing_candidate() -> None:
    plane = FrontierCognitiveControlPlane(
        StubSupervisor([InterventionKind.CONTINUE]),
        policy=_policy(),
        clock=lambda: 100.0,
    )
    baseline = plane.baseline.evaluate(_signals("audit", progress=0.2))
    report = plane._audit_safety(
        baseline,
        InterventionKind.REPLAN,
        robust_ready=True,
    )
    assert not report.risk_nonincreasing
    assert not report.passed
    assert any("risk" in failure for failure in report.failures)


def test_diffuse_posterior_cannot_force_noninformation_override_by_default() -> None:
    # The cold/learning gate is stricter than the diffuse gate, but this test
    # locks the configured invariant itself: when structural uncertainty is
    # diffuse, allowed alternatives are restricted to information-safe kinds.
    policy = _policy()
    assert not policy.allow_override_when_diffuse
    assert InterventionKind.REPLAN not in policy.diffuse_safe_kinds
    assert InterventionKind.SEEK_INFORMATION in policy.diffuse_safe_kinds
    assert InterventionKind.VERIFY in policy.diffuse_safe_kinds


def test_control_plane_fingerprint_changes_after_verified_experience() -> None:
    plane = FrontierCognitiveControlPlane(
        StubSupervisor([InterventionKind.CONTINUE]),
        policy=_policy(),
        clock=lambda: 100.0,
    )
    before = plane.fingerprint
    _feed_transition(
        plane,
        1,
        before_progress=0.1,
        after_progress=0.2,
    )
    assert plane.fingerprint != before
