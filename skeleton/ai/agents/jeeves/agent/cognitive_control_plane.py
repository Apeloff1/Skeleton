"""Robust causal cognitive control plane for Jeeves.

This module is the cross-run control authority above the bounded worker harness.
It combines the conservative live supervisor with verified interventional
learning and Bayesian causal-model uncertainty while preserving a strict
precedence relation:

    hard host safety > verified causal mechanisms > model ensemble
    > robust soft-policy choice > probabilistic worker proposal

The control plane cannot weaken confirmation gates, hard aborts, capability
policy, evidence custody, or host-side verification.  It learns only which
*soft cognitive intervention* (continue, verify, retrieve, redirect, replan,
etc.) tends to improve subsequent verified state.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .causal_ensemble import (
    BayesianCausalEnsemble,
    CausalModelHypothesis,
    EnsemblePolicy,
    RobustActionEvaluation,
    RobustObjective,
)
from .causal_epistemics import (
    CategoricalDistribution,
    CausalMechanism,
    CausalVariable,
    EpistemicAction,
    Preference,
    StructuralCausalModel,
    TransitionSample,
)
from .causal_supervisor import (
    OutcomeClass,
    SupervisorCausalModel,
    SupervisorStateEncoder,
    Trend,
)
from .interventional_learning import (
    BayesianMechanismTrainer,
    MechanismTrainingPolicy,
    MechanismTrainingReport,
    promote_training_report,
)
from .live_supervisor import Intervention, InterventionKind, LiveSupervisor, SupervisorSignals
from .types import (
    AgentContractError,
    RiskTier,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class CognitiveControlError(RuntimeError):
    pass


class ControlReadiness(str, Enum):
    COLD = "cold"
    LEARNING = "learning"
    ROBUST = "robust"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class ControlPlanePolicy:
    minimum_verified_transitions: int = 24
    minimum_action_support: int = 4
    learn_every: int = 8
    ensemble_minimum_models: int = 2
    ensemble_maximum_models: int = 12
    minimum_promoted_targets: int = 4
    minimum_override_gain: float = 0.08
    maximum_override_risk: RiskTier = RiskTier.REVERSIBLE
    robust_objective: RobustObjective = RobustObjective.CVAR
    allow_override_when_diffuse: bool = False
    diffuse_safe_kinds: tuple[InterventionKind, ...] = (
        InterventionKind.SEEK_INFORMATION,
        InterventionKind.VERIFY,
        InterventionKind.CONTINUE,
    )
    history_limit: int = 10_000
    mechanism_policy: MechanismTrainingPolicy = field(
        default_factory=lambda: MechanismTrainingPolicy(
            equivalent_sample_size=4.0,
            minimum_train_samples=12,
            minimum_effective_sample_size=8.0,
            minimum_interventional_parent_samples=3,
            holdout_fraction=0.2,
            minimum_confidence=0.35,
            maximum_log_loss=3.5,
            maximum_brier_score=0.45,
            maximum_ece=0.35,
            calibration_bins=8,
        )
    )
    ensemble_policy: EnsemblePolicy = field(
        default_factory=lambda: EnsemblePolicy(
            lower_confidence_k=1.25,
            cvar_alpha=0.25,
            model_information_weight=0.30,
            cost_weight=0.10,
            safety_weight=0.45,
            collapse_threshold=0.997,
            diffuse_effective_fraction=0.70,
        )
    )

    def __post_init__(self) -> None:
        for name in (
            "minimum_verified_transitions",
            "minimum_action_support",
            "learn_every",
            "ensemble_minimum_models",
            "ensemble_maximum_models",
            "minimum_promoted_targets",
            "history_limit",
        ):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1_000_000))
        if self.ensemble_maximum_models < self.ensemble_minimum_models:
            raise AgentContractError("ensemble maximum must be >= minimum")
        gain = finite_number("minimum_override_gain", self.minimum_override_gain)
        if gain < 0:
            raise AgentContractError("minimum_override_gain must be non-negative")
        object.__setattr__(self, "minimum_override_gain", gain)
        if not isinstance(self.maximum_override_risk, RiskTier):
            object.__setattr__(self, "maximum_override_risk", RiskTier(str(self.maximum_override_risk)))
        if not isinstance(self.robust_objective, RobustObjective):
            object.__setattr__(self, "robust_objective", RobustObjective(str(self.robust_objective)))
        kinds = tuple(kind if isinstance(kind, InterventionKind) else InterventionKind(str(kind)) for kind in self.diffuse_safe_kinds)
        object.__setattr__(self, "diffuse_safe_kinds", kinds)
        if not isinstance(self.mechanism_policy, MechanismTrainingPolicy):
            raise AgentContractError("mechanism_policy must be MechanismTrainingPolicy")
        if not isinstance(self.ensemble_policy, EnsemblePolicy):
            raise AgentContractError("ensemble_policy must be EnsemblePolicy")


@dataclass(frozen=True, slots=True)
class ControlTransition:
    transition_id: str
    run_id: str
    action_kind: InterventionKind
    baseline_intervention_id: str
    before_fingerprint: str
    after_fingerprint: str
    verified: bool
    outcome: OutcomeClass
    trend: Trend
    reward: float
    sample_id: str
    created_at: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class LearningCycle:
    cycle_id: str
    verified_transition_count: int
    reports: tuple[MechanismTrainingReport, ...]
    promoted_targets: tuple[str, ...]
    rejected_targets: tuple[str, ...]
    model_hypothesis_id: str | None
    ensemble_size: int
    created_at: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SafetyInvariantReport:
    baseline_kind: InterventionKind
    candidate_kind: InterventionKind
    hard_baseline_preserved: bool
    confirmation_preserved: bool
    risk_nonincreasing: bool
    action_supported: bool
    robust_evidence_ready: bool
    passed: bool
    failures: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ControlDecision:
    decision_id: str
    run_id: str
    baseline: Intervention
    selected: Intervention
    readiness: ControlReadiness
    baseline_robust_score: float | None
    selected_robust_score: float | None
    expected_gain: float
    posterior_fingerprint: str | None
    posterior_entropy_bits: float | None
    safety: SafetyInvariantReport
    reasons: tuple[str, ...]
    created_at: float
    fingerprint: str


class CausalModelCloner:
    @staticmethod
    def clone(source: StructuralCausalModel) -> StructuralCausalModel:
        clone = StructuralCausalModel(max_joint_states=source.max_joint_states)
        for variable in source.variables():
            clone.add_variable(variable)
        clone.set_regime(source.active_regime)
        for variable in source.variables():
            mechanism = source.mechanism(variable.variable_id, regime=source.active_regime)
            if mechanism is not None:
                clone.set_mechanism(mechanism)
        return clone


class CognitiveControlPlane:
    HARD_KINDS = frozenset({
        InterventionKind.ABORT_RUN,
        InterventionKind.REQUEST_CONFIRMATION,
        InterventionKind.ABORT_OPTION,
    })
    LEARNABLE_KINDS = (
        InterventionKind.CONTINUE,
        InterventionKind.REDIRECT,
        InterventionKind.REPLAN,
        InterventionKind.SEEK_INFORMATION,
        InterventionKind.VERIFY,
        InterventionKind.SUSPEND_INTENTION,
        InterventionKind.SWITCH_INTENTION,
    )
    TARGETS: Mapping[str, tuple[str, ...]] = {
        "n_progress": ("control_action", "s_progress", "s_failures", "s_ready_steps"),
        "n_failures": ("control_action", "s_failures", "s_risk"),
        "n_verification_failures": ("control_action", "s_verification_failures", "s_risk"),
        "n_uncertainty": ("control_action", "s_uncertainty", "s_contradiction", "s_evidence_growth"),
        "n_contradiction": ("control_action", "s_contradiction", "s_uncertainty"),
        "n_loop": ("control_action", "s_loop", "s_staleness"),
        "n_evidence_growth": ("control_action", "s_evidence_growth", "s_staleness"),
        "n_budget": ("control_action", "s_budget"),
        "outcome": ("control_action", "s_progress", "s_failures", "s_uncertainty", "s_loop", "s_risk"),
    }
    _RISK_LEVEL = {
        RiskTier.READ_ONLY: 0,
        RiskTier.REVERSIBLE: 1,
        RiskTier.MUTATING: 2,
        RiskTier.EXTERNAL: 3,
        RiskTier.HIGH_IMPACT: 4,
    }

    def __init__(
        self,
        baseline: LiveSupervisor | None = None,
        *,
        policy: ControlPlanePolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or ControlPlanePolicy()
        self._clock = clock
        self.baseline = baseline or LiveSupervisor(clock=clock)
        self.encoder = SupervisorStateEncoder()
        template = SupervisorCausalModel()
        self._preferences = template.kernel.planner.preferences
        self._model = template.model
        self._trainer = BayesianMechanismTrainer(self._model, policy=self.policy.mechanism_policy)
        self._ensemble = BayesianCausalEnsemble(
            preferences=self._preferences,
            policy=self.policy.ensemble_policy,
            clock=clock,
            history_limit=self.policy.history_limit,
        )
        self._pending: dict[str, tuple[Any, Intervention]] = {}
        self._transitions: deque[ControlTransition] = deque(maxlen=self.policy.history_limit)
        self._cycles: deque[LearningCycle] = deque(maxlen=self.policy.history_limit)
        self._decisions: deque[ControlDecision] = deque(maxlen=self.policy.history_limit)
        self._support: Counter[str] = Counter()
        self._promoted_targets: set[str] = set()
        self._model_hypothesis_ids: deque[str] = deque()
        self._lock = threading.RLock()

    @property
    def readiness(self) -> ControlReadiness:
        verified = sum(1 for item in self._transitions if item.verified)
        if verified < self.policy.minimum_verified_transitions:
            return ControlReadiness.COLD
        if len(self._promoted_targets) < self.policy.minimum_promoted_targets:
            return ControlReadiness.LEARNING
        if len(self._ensemble.hypotheses()) < self.policy.ensemble_minimum_models:
            return ControlReadiness.LEARNING
        health = self._ensemble.health()
        if health.stale:
            return ControlReadiness.DEGRADED
        return ControlReadiness.ROBUST

    def evaluate(self, signals: SupervisorSignals) -> Intervention:
        if not isinstance(signals, SupervisorSignals):
            raise TypeError("signals must be SupervisorSignals")
        baseline = self.baseline.evaluate(signals)
        encoded = self.encoder.encode(signals)
        with self._lock:
            self._pending[signals.run_id] = (encoded, baseline)
        selected, decision = self._select(signals, baseline, encoded)
        with self._lock:
            self._decisions.append(decision)
        return selected

    def observe_next(self, signals: SupervisorSignals, *, verified: bool) -> ControlTransition | None:
        if not isinstance(signals, SupervisorSignals):
            raise TypeError("signals must be SupervisorSignals")
        after = self.encoder.encode(signals)
        with self._lock:
            pending = self._pending.pop(signals.run_id, None)
        if pending is None:
            return None
        before, intervention = pending
        outcome, trend, reward = self.encoder.classify_outcome(before, after, verified=verified)
        transition_id = stable_id("control-transition", {
            "run": signals.run_id,
            "before": before.fingerprint,
            "action": intervention.kind.value,
            "after": after.fingerprint,
            "verified": verified,
        })
        # Parent interventions are represented in `interventions`; the stronger
        # BayesianMechanismTrainer resolves them before observed before/after
        # values.  Child interventions would be excluded by that trainer.
        sample = TransitionSample(
            sample_id=stable_id("control-sample", {"transition": transition_id}),
            before={f"s_{key}": value for key, value in before.values.items()},
            interventions={"control_action": intervention.kind.value},
            after={
                "n_progress": after.values["progress"],
                "n_budget": after.values["budget"],
                "n_failures": after.values["failures"],
                "n_verification_failures": after.values["verification_failures"],
                "n_uncertainty": after.values["uncertainty"],
                "n_contradiction": after.values["contradiction"],
                "n_loop": after.values["loop"],
                "n_evidence_growth": after.values["evidence_growth"],
                "outcome": outcome.value,
            },
            verified=verified,
            weight=1.0 if verified else 0.1,
            source_run_id=signals.run_id,
            observed_at=self._clock(),
            metadata={
                "trend": trend.value,
                "reward": reward,
                "intervention_id": intervention.intervention_id,
            },
        )
        record = ControlTransition(
            transition_id=transition_id,
            run_id=signals.run_id,
            action_kind=intervention.kind,
            baseline_intervention_id=intervention.intervention_id,
            before_fingerprint=before.fingerprint,
            after_fingerprint=after.fingerprint,
            verified=verified,
            outcome=outcome,
            trend=trend,
            reward=reward,
            sample_id=sample.sample_id,
            created_at=self._clock(),
            fingerprint=stable_fingerprint({
                "transition": transition_id,
                "sample": sample.sample_id,
                "outcome": outcome.value,
                "reward": reward,
            }),
        )
        with self._lock:
            self._transitions.append(record)
            if verified:
                self._support[intervention.kind.value] += 1
            verified_count = sum(1 for item in self._transitions if item.verified)
        self._record_sample(sample)
        if verified and verified_count >= self.policy.minimum_verified_transitions and verified_count % self.policy.learn_every == 0:
            self._learn_cycle(verified_count)
        return record

    def _record_sample(self, sample: TransitionSample) -> None:
        # Keep a private training ledger.  Ensemble hypotheses are frozen model
        # snapshots; training continues against the mutable current model only.
        if not hasattr(self, "_samples"):
            self._samples: deque[TransitionSample] = deque(maxlen=self.policy.history_limit)
        self._samples.append(sample)

    def _learn_cycle(self, verified_count: int) -> LearningCycle:
        reports: list[MechanismTrainingReport] = []
        promoted: list[str] = []
        rejected: list[str] = []
        samples = tuple(getattr(self, "_samples", ()))
        # Fit every target against the same immutable sample cut.  Promotions
        # occur only after all reports are produced, preventing target order from
        # changing the data or validation metrics within a cycle.
        for child_id, parents in self.TARGETS.items():
            try:
                report = self._trainer.train(child_id, parents, samples)
                reports.append(report)
                if report.promotable:
                    promoted.append(child_id)
                else:
                    rejected.append(child_id)
            except Exception:
                rejected.append(child_id)
        for report in reports:
            if not report.promotable:
                continue
            current = self._model.mechanism(report.child_id)
            learned = promote_training_report(report, current=current)
            # Promotion can still fail if the resulting graph would violate the
            # SCM contract.  Keep the old mechanism in that case.
            try:
                self._model.set_mechanism(learned)
                self._promoted_targets.add(report.child_id)
            except Exception:
                rejected.append(report.child_id)
                if report.child_id in promoted:
                    promoted.remove(report.child_id)
        hypothesis_id = None
        if promoted:
            hypothesis_id = self._snapshot_model(reports)
        cycle_id = stable_id("control-learning-cycle", {
            "verified": verified_count,
            "reports": [report.fingerprint for report in reports],
            "promoted": promoted,
            "model": self._model.fingerprint,
        })
        cycle = LearningCycle(
            cycle_id=cycle_id,
            verified_transition_count=verified_count,
            reports=tuple(reports),
            promoted_targets=tuple(sorted(set(promoted))),
            rejected_targets=tuple(sorted(set(rejected))),
            model_hypothesis_id=hypothesis_id,
            ensemble_size=len(self._ensemble.hypotheses()),
            created_at=self._clock(),
            fingerprint=stable_fingerprint({
                "cycle": cycle_id,
                "model": self._model.fingerprint,
                "ensemble": self._ensemble.fingerprint if self._ensemble.hypotheses() else None,
            }),
        )
        with self._lock:
            self._cycles.append(cycle)
        return cycle

    def _snapshot_model(self, reports: Sequence[MechanismTrainingReport]) -> str:
        clone = CausalModelCloner.clone(self._model)
        confidence_values = [report.confidence for report in reports if report.promotable]
        reliability = sum(confidence_values) / len(confidence_values) if confidence_values else 0.5
        hypothesis_id = stable_id("control-model", {
            "model": clone.fingerprint,
            "cycle": len(self._cycles) + 1,
        })
        hypothesis = CausalModelHypothesis(
            hypothesis_id=hypothesis_id,
            model=clone,
            log_prior_weight=0.0,
            reliability=reliability,
            provenance=tuple(report.report_id for report in reports if report.promotable),
            description="Frozen verified supervisor-control model revision.",
            metadata={"promoted_targets": sorted(self._promoted_targets)},
        )
        self._ensemble.add_hypothesis(hypothesis)
        self._model_hypothesis_ids.append(hypothesis_id)
        self._prune_ensemble()
        return hypothesis_id

    def _prune_ensemble(self) -> None:
        hypotheses = self._ensemble.hypotheses()
        if len(hypotheses) <= self.policy.ensemble_maximum_models:
            return
        posterior = self._ensemble.posterior()
        ordered = sorted(
            hypotheses,
            key=lambda item: (posterior.weights[item.hypothesis_id], item.hypothesis_id),
        )
        remove_count = len(hypotheses) - self.policy.ensemble_maximum_models
        for hypothesis in ordered[:remove_count]:
            self._ensemble.remove_hypothesis(hypothesis.hypothesis_id)
            try:
                self._model_hypothesis_ids.remove(hypothesis.hypothesis_id)
            except ValueError:
                pass

    def update_model_posterior(
        self,
        observation: Mapping[str, str],
        *,
        state_evidence: Mapping[str, str] | None = None,
        control_action: InterventionKind | None = None,
    ) -> Any | None:
        if not self._ensemble.hypotheses():
            return None
        interventions = {"control_action": control_action.value} if control_action is not None else {}
        return self._ensemble.update(
            observation,
            conditioning_evidence=state_evidence,
            interventions=interventions,
        )

    def _select(self, signals: SupervisorSignals, baseline: Intervention, encoded: Any) -> tuple[Intervention, ControlDecision]:
        readiness = self.readiness
        reasons: list[str] = []
        if baseline.kind in self.HARD_KINDS or baseline.hard:
            reasons.append("hard baseline is immutable")
            safety = self._audit_safety(baseline, baseline.kind, robust_ready=False)
            return baseline, self._decision(signals, baseline, baseline, readiness, None, None, 0.0, None, safety, reasons)
        if readiness is not ControlReadiness.ROBUST:
            reasons.append(f"control plane readiness={readiness.value}; baseline retained")
            safety = self._audit_safety(baseline, baseline.kind, robust_ready=False)
            return baseline, self._decision(signals, baseline, baseline, readiness, None, None, 0.0, None, safety, reasons)
        health = self._ensemble.health()
        actions = self._candidate_actions(baseline, signals, health.diffuse)
        state_evidence = {f"s_{key}": value for key, value in encoded.values.items()}
        if not actions:
            reasons.append("no supported soft alternatives")
            safety = self._audit_safety(baseline, baseline.kind, robust_ready=True)
            return baseline, self._decision(signals, baseline, baseline, readiness, None, None, 0.0, health, safety, reasons)
        try:
            ranking = self._ensemble.rank_actions(
                actions,
                evidence=state_evidence,
                objective=self.policy.robust_objective,
                maximum_risk=self.policy.maximum_override_risk,
            )
        except Exception as exc:
            reasons.append(f"robust causal ranking unavailable: {type(exc).__name__}")
            safety = self._audit_safety(baseline, baseline.kind, robust_ready=False)
            return baseline, self._decision(signals, baseline, baseline, readiness, None, None, 0.0, health, safety, reasons)
        by_kind = {self._kind_from_action(item.action_id): item for item in ranking}
        baseline_eval = by_kind.get(baseline.kind)
        if baseline_eval is None:
            reasons.append("baseline lacks robust support; no override")
            safety = self._audit_safety(baseline, baseline.kind, robust_ready=False)
            return baseline, self._decision(signals, baseline, baseline, readiness, None, None, 0.0, health, safety, reasons)
        best = ranking[0]
        selected_kind = self._kind_from_action(best.action_id)
        gain = best.robust_score - baseline_eval.robust_score
        safety = self._audit_safety(baseline, selected_kind, robust_ready=True)
        if selected_kind == baseline.kind:
            reasons.append("robust ensemble agrees with baseline")
            return baseline, self._decision(signals, baseline, baseline, readiness, baseline_eval.robust_score, best.robust_score, gain, health, safety, reasons)
        if gain < self.policy.minimum_override_gain:
            reasons.append(f"robust gain {gain:.4f} below override margin")
            return baseline, self._decision(signals, baseline, baseline, readiness, baseline_eval.robust_score, best.robust_score, gain, health, safety, reasons)
        if health.diffuse and not self.policy.allow_override_when_diffuse and selected_kind not in self.policy.diffuse_safe_kinds:
            reasons.append("posterior structurally diffuse; only information/verification overrides allowed")
            return baseline, self._decision(signals, baseline, baseline, readiness, baseline_eval.robust_score, best.robust_score, gain, health, safety, reasons)
        if not safety.passed:
            reasons.extend(safety.failures)
            return baseline, self._decision(signals, baseline, baseline, readiness, baseline_eval.robust_score, best.robust_score, gain, health, safety, reasons)
        reasons.append(f"robust ensemble selects {selected_kind.value} with gain {gain:.4f}")
        selected = self._make_override(baseline, selected_kind, gain, best, health.fingerprint)
        return selected, self._decision(signals, baseline, selected, readiness, baseline_eval.robust_score, best.robust_score, gain, health, safety, reasons)

    def _candidate_actions(self, baseline: Intervention, signals: SupervisorSignals, diffuse: bool) -> tuple[EpistemicAction, ...]:
        kinds = set(self.LEARNABLE_KINDS)
        kinds.add(baseline.kind)
        actions: list[EpistemicAction] = []
        for kind in sorted(kinds, key=lambda item: item.value):
            if kind in self.HARD_KINDS:
                continue
            if self._support[kind.value] < self.policy.minimum_action_support and kind != baseline.kind:
                continue
            if self._RISK_LEVEL[self._kind_risk(kind)] > self._RISK_LEVEL[self.policy.maximum_override_risk]:
                continue
            if diffuse and not self.policy.allow_override_when_diffuse and kind not in self.policy.diffuse_safe_kinds and kind != baseline.kind:
                continue
            actions.append(EpistemicAction(
                action_id=f"control:{kind.value}",
                interventions={"control_action": kind.value},
                observation_targets=("n_progress", "n_failures", "n_verification_failures", "n_uncertainty", "n_loop", "outcome"),
                base_cost=self._kind_cost(kind),
                risk=self._kind_risk(kind),
                reversible=True,
                description=f"Supervisor cognitive intervention: {kind.value}",
            ))
        return tuple(actions)

    def _audit_safety(self, baseline: Intervention, candidate: InterventionKind, *, robust_ready: bool) -> SafetyInvariantReport:
        failures: list[str] = []
        hard_preserved = baseline.kind not in self.HARD_KINDS or candidate == baseline.kind
        if not hard_preserved:
            failures.append("hard baseline intervention changed")
        confirmation_preserved = baseline.kind is not InterventionKind.REQUEST_CONFIRMATION or candidate is InterventionKind.REQUEST_CONFIRMATION
        if not confirmation_preserved:
            failures.append("confirmation gate weakened")
        risk_ok = self._RISK_LEVEL[self._kind_risk(candidate)] <= self._RISK_LEVEL[self._kind_risk(baseline.kind)]
        if not risk_ok:
            failures.append("candidate increases control risk")
        supported = candidate == baseline.kind or self._support[candidate.value] >= self.policy.minimum_action_support
        if not supported:
            failures.append("candidate lacks verified action support")
        if not robust_ready and candidate != baseline.kind:
            failures.append("robust causal evidence not ready")
        passed = hard_preserved and confirmation_preserved and risk_ok and supported and (robust_ready or candidate == baseline.kind)
        return SafetyInvariantReport(
            baseline_kind=baseline.kind,
            candidate_kind=candidate,
            hard_baseline_preserved=hard_preserved,
            confirmation_preserved=confirmation_preserved,
            risk_nonincreasing=risk_ok,
            action_supported=supported,
            robust_evidence_ready=robust_ready,
            passed=passed,
            failures=tuple(failures),
            fingerprint=stable_fingerprint({
                "baseline": baseline.kind.value,
                "candidate": candidate.value,
                "hard": hard_preserved,
                "confirmation": confirmation_preserved,
                "risk": risk_ok,
                "support": supported,
                "robust": robust_ready,
            }),
        )

    def _make_override(self, baseline: Intervention, kind: InterventionKind, gain: float, evaluation: RobustActionEvaluation, posterior_fingerprint: str) -> Intervention:
        return Intervention(
            intervention_id=stable_id("robust-control", {
                "baseline": baseline.intervention_id,
                "kind": kind.value,
                "evaluation": evaluation.fingerprint,
                "posterior": posterior_fingerprint,
            }),
            run_id=baseline.run_id,
            kind=kind,
            reason=f"Robust causal control selected {kind.value}; CVaR/model-uncertainty adjusted gain={gain:.4f}.",
            priority=min(0.94, max(baseline.priority, 0.55 + min(0.35, max(0.0, gain)))),
            created_at=self._clock(),
            target_intention_id=baseline.target_intention_id,
            target_option_execution_id=baseline.target_option_execution_id,
            directive=self._directive(kind),
            evidence_ids=baseline.evidence_ids,
            expected_effect=f"Improve next verified checkpoint under causal model uncertainty; robust gain={gain:.4f}.",
            hard=False,
            metadata={
                **dict(baseline.metadata),
                "robust_causal_override": True,
                "baseline_intervention_id": baseline.intervention_id,
                "baseline_kind": baseline.kind.value,
                "robust_evaluation": evaluation.fingerprint,
                "posterior_fingerprint": posterior_fingerprint,
            },
        )

    def _decision(self, signals: SupervisorSignals, baseline: Intervention, selected: Intervention, readiness: ControlReadiness, baseline_score: float | None, selected_score: float | None, gain: float, health: Any | None, safety: SafetyInvariantReport, reasons: Sequence[str]) -> ControlDecision:
        decision_id = stable_id("control-decision", {
            "run": signals.run_id,
            "baseline": baseline.intervention_id,
            "selected": selected.intervention_id,
            "readiness": readiness.value,
            "gain": gain,
            "model": self._ensemble.fingerprint if self._ensemble.hypotheses() else self._model.fingerprint,
        })
        posterior = self._ensemble.posterior() if self._ensemble.hypotheses() else None
        return ControlDecision(
            decision_id=decision_id,
            run_id=signals.run_id,
            baseline=baseline,
            selected=selected,
            readiness=readiness,
            baseline_robust_score=baseline_score,
            selected_robust_score=selected_score,
            expected_gain=gain,
            posterior_fingerprint=posterior.fingerprint if posterior else None,
            posterior_entropy_bits=posterior.entropy_bits if posterior else None,
            safety=safety,
            reasons=tuple(reasons),
            created_at=self._clock(),
            fingerprint=stable_fingerprint({
                "decision": decision_id,
                "safety": safety.fingerprint,
                "reasons": list(reasons),
            }),
        )

    @staticmethod
    def _kind_from_action(action_id: str) -> InterventionKind:
        if not action_id.startswith("control:"):
            raise CognitiveControlError(f"unknown control action id: {action_id}")
        return InterventionKind(action_id.split(":", 1)[1])

    @staticmethod
    def _kind_risk(kind: InterventionKind) -> RiskTier:
        if kind in {InterventionKind.CONTINUE, InterventionKind.SEEK_INFORMATION, InterventionKind.VERIFY, InterventionKind.PAUSE}:
            return RiskTier.READ_ONLY
        if kind in {InterventionKind.REDIRECT, InterventionKind.REPLAN, InterventionKind.SUSPEND_INTENTION, InterventionKind.SWITCH_INTENTION}:
            return RiskTier.REVERSIBLE
        return RiskTier.HIGH_IMPACT

    @staticmethod
    def _kind_cost(kind: InterventionKind) -> float:
        return {
            InterventionKind.CONTINUE: 0.05,
            InterventionKind.REDIRECT: 0.16,
            InterventionKind.REPLAN: 0.38,
            InterventionKind.SEEK_INFORMATION: 0.24,
            InterventionKind.VERIFY: 0.20,
            InterventionKind.SUSPEND_INTENTION: 0.14,
            InterventionKind.SWITCH_INTENTION: 0.30,
            InterventionKind.PAUSE: 0.10,
            InterventionKind.REQUEST_CONFIRMATION: 0.10,
            InterventionKind.ABORT_OPTION: 0.25,
            InterventionKind.ABORT_RUN: 1.0,
        }[kind]

    @staticmethod
    def _directive(kind: InterventionKind) -> str:
        return {
            InterventionKind.CONTINUE: "Continue the current verified tactical path.",
            InterventionKind.REDIRECT: "Change tactic while preserving verified work and constraints.",
            InterventionKind.REPLAN: "Replan only the invalid frontier from the current verified state.",
            InterventionKind.SEEK_INFORMATION: "Acquire the observation with best information gain per cost and risk.",
            InterventionKind.VERIFY: "Spend the next control interval on independent verification.",
            InterventionKind.SUSPEND_INTENTION: "Suspend the current intention while preserving resumable state.",
            InterventionKind.SWITCH_INTENTION: "Switch to the supported higher-value intention.",
            InterventionKind.PAUSE: "Pause and checkpoint state.",
            InterventionKind.REQUEST_CONFIRMATION: "Request explicit confirmation.",
            InterventionKind.ABORT_OPTION: "Abort the current temporal option safely.",
            InterventionKind.ABORT_RUN: "Abort the run safely and preserve forensic state.",
        }[kind]

    def transitions(self, *, verified_only: bool = False) -> tuple[ControlTransition, ...]:
        with self._lock:
            values = tuple(self._transitions)
        return tuple(item for item in values if item.verified) if verified_only else values

    def cycles(self) -> tuple[LearningCycle, ...]:
        with self._lock:
            return tuple(self._cycles)

    def decisions(self, *, run_id: str | None = None) -> tuple[ControlDecision, ...]:
        with self._lock:
            values = tuple(self._decisions)
        if run_id is not None:
            run_id = require_id("run_id", run_id)
            values = tuple(item for item in values if item.run_id == run_id)
        return values

    def summary(self) -> dict[str, Any]:
        verified = len(self.transitions(verified_only=True))
        ensemble_summary = self._ensemble.summary() if self._ensemble.hypotheses() else None
        return {
            "readiness": self.readiness.value,
            "transitions": len(self._transitions),
            "verified_transitions": verified,
            "action_support": dict(sorted(self._support.items())),
            "promoted_targets": sorted(self._promoted_targets),
            "learning_cycles": len(self._cycles),
            "decisions": len(self._decisions),
            "ensemble": ensemble_summary,
            "current_model_fingerprint": self._model.fingerprint,
            "fingerprint": self.fingerprint,
        }

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "readiness": self.readiness.value,
            "model": self._model.fingerprint,
            "ensemble": self._ensemble.fingerprint if self._ensemble.hypotheses() else None,
            "support": dict(sorted(self._support.items())),
            "promoted": sorted(self._promoted_targets),
            "transitions": [item.fingerprint for item in self._transitions],
            "cycles": [item.fingerprint for item in self._cycles],
            "decisions": [item.fingerprint for item in self._decisions],
        })
