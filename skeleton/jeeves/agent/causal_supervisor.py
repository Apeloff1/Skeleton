"""Causal policy-improvement layer for Jeeves' live supervisor.

The rule-driven ``LiveSupervisor`` remains the hard safety baseline.  This
module learns which *soft* cognitive interventions improve the next verified
checkpoint in which regimes, then permits an override only when there is
adequate host-verified support, promoted causal mechanisms, a material expected
utility gain, and no increase in control risk.

Hard aborts, confirmation gates, and option-abort safety decisions are never
learned away.  The causal layer may improve tactics; it may not weaken policy.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .causal_epistemics import (
    CategoricalDistribution,
    CausalEpistemicKernel,
    CausalEpistemicError,
    CausalVariable,
    EpistemicAction,
    Preference,
    StructuralCausalModel,
    TransitionSample,
    VariableRole,
)
from .live_supervisor import Intervention, InterventionKind, LiveSupervisor, SupervisorSignals
from .types import (
    AgentContractError,
    RiskTier,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class CausalSupervisorError(RuntimeError):
    pass


class Bucket(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProgressBucket(str, Enum):
    NONE = "none"
    EARLY = "early"
    MID = "mid"
    LATE = "late"
    COMPLETE = "complete"


class Trend(str, Enum):
    STRONGLY_WORSE = "strongly_worse"
    WORSE = "worse"
    FLAT = "flat"
    BETTER = "better"
    STRONGLY_BETTER = "strongly_better"


class OutcomeClass(str, Enum):
    IMPROVED = "improved"
    NEUTRAL = "neutral"
    DEGRADED = "degraded"
    FAILED = "failed"


_RISK_LEVEL = {
    RiskTier.READ_ONLY: 0,
    RiskTier.REVERSIBLE: 1,
    RiskTier.MUTATING: 2,
    RiskTier.EXTERNAL: 3,
    RiskTier.HIGH_IMPACT: 4,
}


@dataclass(frozen=True, slots=True)
class EncodedSupervisorState:
    run_id: str
    values: Mapping[str, str]
    continuous: Mapping[str, float]
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        values = {require_id("state variable", key): str(value) for key, value in dict(self.values).items()}
        continuous = {require_id("continuous variable", key): finite_number(key, value) for key, value in dict(self.continuous).items()}
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "continuous", continuous)
        fp = str(self.fingerprint).strip().lower()
        if len(fp) != 64 or any(ch not in "0123456789abcdef" for ch in fp):
            raise AgentContractError("encoded state fingerprint must be sha256 hex")
        object.__setattr__(self, "fingerprint", fp)


class SupervisorStateEncoder:
    """Project high-dimensional supervisor state into stable causal categories."""

    @staticmethod
    def _bucket(value: float) -> Bucket:
        value = max(0.0, min(1.0, float(value)))
        if value <= 0.0:
            return Bucket.NONE
        if value < 0.30:
            return Bucket.LOW
        if value < 0.60:
            return Bucket.MEDIUM
        if value < 0.85:
            return Bucket.HIGH
        return Bucket.CRITICAL

    @staticmethod
    def _progress(value: float) -> ProgressBucket:
        value = max(0.0, min(1.0, float(value)))
        if value <= 0.0:
            return ProgressBucket.NONE
        if value < 0.25:
            return ProgressBucket.EARLY
        if value < 0.60:
            return ProgressBucket.MID
        if value < 1.0:
            return ProgressBucket.LATE
        return ProgressBucket.COMPLETE

    @staticmethod
    def _count(value: int) -> str:
        if value <= 0:
            return "0"
        if value == 1:
            return "1"
        if value <= 3:
            return "2_3"
        return "4_plus"

    def encode(self, signals: SupervisorSignals) -> EncodedSupervisorState:
        if not isinstance(signals, SupervisorSignals):
            raise TypeError("signals must be SupervisorSignals")
        uncertainty = 1.0 - signals.belief.maximum_probability
        values = {
            "phase": signals.phase.value,
            "progress": self._progress(signals.progress).value,
            "budget": self._bucket(signals.budget_pressure).value,
            "failures": self._count(signals.failure_streak),
            "verification_failures": self._count(signals.verification_failure_streak),
            "replans": self._count(signals.replans),
            "ready_steps": self._count(signals.plan_ready_steps),
            "failed_steps": self._count(signals.plan_failed_steps),
            "blocked_steps": self._count(signals.plan_blocked_steps),
            "uncertainty": self._bucket(uncertainty).value,
            "contradiction": self._bucket(signals.belief.contradiction_pressure).value,
            "loop": self._bucket(signals.loop_severity).value,
            "evidence_growth": self._count(signals.evidence_growth),
            "staleness": self._count(signals.stale_cycles),
            "risk": signals.current_risk.value,
            "pending_confirmation": "yes" if signals.pending_confirmation else "no",
        }
        continuous = {
            "progress": signals.progress,
            "budget": signals.budget_pressure,
            "uncertainty": uncertainty,
            "contradiction": signals.belief.contradiction_pressure,
            "loop": signals.loop_severity,
        }
        return EncodedSupervisorState(
            run_id=signals.run_id,
            values=values,
            continuous=continuous,
            fingerprint=stable_fingerprint({"values": values, "continuous": continuous}),
        )

    def classify_outcome(
        self,
        before: EncodedSupervisorState,
        after: EncodedSupervisorState,
        *,
        verified: bool,
    ) -> tuple[OutcomeClass, Trend, float]:
        if before.run_id != after.run_id:
            raise CausalSupervisorError("cannot classify transition across runs")
        b = before.continuous
        a = after.continuous
        delta_progress = a["progress"] - b["progress"]
        delta_fail = self._failure_load(after.values) - self._failure_load(before.values)
        delta_uncertainty = b["uncertainty"] - a["uncertainty"]
        delta_loop = b["loop"] - a["loop"]
        delta_budget = b["budget"] - a["budget"]
        score = (
            delta_progress * 0.48
            + delta_uncertainty * 0.17
            + delta_loop * 0.13
            + delta_fail * 0.16
            + delta_budget * 0.06
        )
        if not verified:
            score *= 0.20
        if score >= 0.20:
            return OutcomeClass.IMPROVED, Trend.STRONGLY_BETTER, score
        if score >= 0.04:
            return OutcomeClass.IMPROVED, Trend.BETTER, score
        if score <= -0.20:
            return OutcomeClass.FAILED, Trend.STRONGLY_WORSE, score
        if score <= -0.04:
            return OutcomeClass.DEGRADED, Trend.WORSE, score
        return OutcomeClass.NEUTRAL, Trend.FLAT, score

    @staticmethod
    def _failure_load(values: Mapping[str, str]) -> float:
        weights = {"0": 0.0, "1": -0.25, "2_3": -0.60, "4_plus": -1.0}
        return weights.get(values.get("failures", "0"), 0.0) * 0.6 + weights.get(values.get("verification_failures", "0"), 0.0) * 0.4


@dataclass(frozen=True, slots=True)
class CausalControlConfig:
    minimum_verified_transitions: int = 24
    minimum_action_support: int = 5
    learn_every: int = 8
    minimum_promoted_mechanisms: int = 3
    minimum_override_gain: float = 0.10
    minimum_mechanism_confidence: float = 0.50
    maximum_heldout_log_loss: float = 4.0
    drift_guard_bits: float = 0.45
    maximum_override_risk: RiskTier = RiskTier.REVERSIBLE
    enable_overrides: bool = True
    history_limit: int = 4096

    def __post_init__(self) -> None:
        for name in (
            "minimum_verified_transitions",
            "minimum_action_support",
            "learn_every",
            "minimum_promoted_mechanisms",
            "history_limit",
        ):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1_000_000))
        gain = finite_number("minimum_override_gain", self.minimum_override_gain)
        if gain < 0:
            raise AgentContractError("minimum_override_gain must be non-negative")
        object.__setattr__(self, "minimum_override_gain", gain)
        object.__setattr__(self, "minimum_mechanism_confidence", probability("minimum_mechanism_confidence", self.minimum_mechanism_confidence))
        loss = finite_number("maximum_heldout_log_loss", self.maximum_heldout_log_loss)
        if loss < 0:
            raise AgentContractError("maximum heldout loss must be non-negative")
        object.__setattr__(self, "maximum_heldout_log_loss", loss)
        drift = finite_number("drift_guard_bits", self.drift_guard_bits)
        if drift < 0:
            raise AgentContractError("drift guard must be non-negative")
        object.__setattr__(self, "drift_guard_bits", drift)
        if not isinstance(self.maximum_override_risk, RiskTier):
            object.__setattr__(self, "maximum_override_risk", RiskTier(str(self.maximum_override_risk)))


@dataclass(frozen=True, slots=True)
class CausalControlTransition:
    transition_id: str
    run_id: str
    baseline_intervention_id: str
    action_kind: InterventionKind
    before: EncodedSupervisorState
    after: EncodedSupervisorState
    verified: bool
    outcome: OutcomeClass
    trend: Trend
    reward: float
    sample_id: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class CausalSupervisorAssessment:
    assessment_id: str
    run_id: str
    baseline: Intervention
    recommended_kind: InterventionKind
    baseline_expected_utility: float | None
    recommended_expected_utility: float | None
    expected_gain: float
    override_allowed: bool
    support: Mapping[str, int]
    promoted_mechanisms: int
    reasons: tuple[str, ...]
    model_fingerprint: str
    fingerprint: str


class SupervisorCausalModel:
    """SCM over supervisor state, cognitive intervention, and next checkpoint."""

    CONTROL_DOMAIN = tuple(kind.value for kind in InterventionKind)
    BUCKET_DOMAIN = tuple(item.value for item in Bucket)
    PROGRESS_DOMAIN = tuple(item.value for item in ProgressBucket)
    COUNT_DOMAIN = ("0", "1", "2_3", "4_plus")

    def __init__(self) -> None:
        self.model = StructuralCausalModel(max_joint_states=250_000)
        self._build_variables()
        preferences = (
            Preference("n_progress", CategoricalDistribution({"none": 0.01, "early": 0.04, "mid": 0.10, "late": 0.25, "complete": 0.60}, self.PROGRESS_DOMAIN), 2.0),
            Preference("n_failures", CategoricalDistribution({"0": 0.78, "1": 0.15, "2_3": 0.06, "4_plus": 0.01}, self.COUNT_DOMAIN), 1.2),
            Preference("n_verification_failures", CategoricalDistribution({"0": 0.82, "1": 0.12, "2_3": 0.05, "4_plus": 0.01}, self.COUNT_DOMAIN), 1.3),
            Preference("n_uncertainty", CategoricalDistribution({"none": 0.35, "low": 0.42, "medium": 0.16, "high": 0.06, "critical": 0.01}, self.BUCKET_DOMAIN), 0.8),
            Preference("n_loop", CategoricalDistribution({"none": 0.55, "low": 0.30, "medium": 0.10, "high": 0.04, "critical": 0.01}, self.BUCKET_DOMAIN), 0.7),
            Preference("outcome", CategoricalDistribution({"improved": 0.70, "neutral": 0.22, "degraded": 0.07, "failed": 0.01}, tuple(item.value for item in OutcomeClass)), 1.5),
        )
        self.kernel = CausalEpistemicKernel(self.model, preferences=preferences)

    def _add(self, variable_id: str, domain: Sequence[str], *, role: VariableRole = VariableRole.STATE, manipulable: bool = False) -> None:
        self.model.add_variable(CausalVariable(variable_id, tuple(domain), role=role, manipulable=manipulable, risk=RiskTier.READ_ONLY))

    def _build_variables(self) -> None:
        self._add("s_phase", tuple(item.value for item in __import__("skeleton.jeeves.agent.types", fromlist=["AgentPhase"]).AgentPhase), role=VariableRole.CONTEXT)
        self._add("s_progress", self.PROGRESS_DOMAIN)
        self._add("s_budget", self.BUCKET_DOMAIN)
        for name in ("s_failures", "s_verification_failures", "s_replans", "s_ready_steps", "s_failed_steps", "s_blocked_steps", "s_evidence_growth", "s_staleness"):
            self._add(name, self.COUNT_DOMAIN)
        for name in ("s_uncertainty", "s_contradiction", "s_loop"):
            self._add(name, self.BUCKET_DOMAIN)
        self._add("s_risk", tuple(item.value for item in RiskTier), role=VariableRole.CONTEXT)
        self._add("s_pending_confirmation", ("no", "yes"), role=VariableRole.CONTEXT)
        self._add("control_action", self.CONTROL_DOMAIN, role=VariableRole.ACTION, manipulable=True)
        self._add("n_progress", self.PROGRESS_DOMAIN, role=VariableRole.OUTCOME)
        self._add("n_budget", self.BUCKET_DOMAIN, role=VariableRole.OUTCOME)
        for name in ("n_failures", "n_verification_failures", "n_evidence_growth"):
            self._add(name, self.COUNT_DOMAIN, role=VariableRole.OUTCOME)
        for name in ("n_uncertainty", "n_contradiction", "n_loop"):
            self._add(name, self.BUCKET_DOMAIN, role=VariableRole.OUTCOME)
        self._add("outcome", tuple(item.value for item in OutcomeClass), role=VariableRole.OUTCOME)


class CausalSupervisorLearner:
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

    def __init__(self, causal_model: SupervisorCausalModel, config: CausalControlConfig) -> None:
        self.causal_model = causal_model
        self.config = config
        self.promoted: set[str] = set()
        self.failed_promotions: Counter[str] = Counter()

    def maybe_learn(self, verified_transitions: int) -> tuple[str, ...]:
        if verified_transitions < self.config.minimum_verified_transitions:
            return ()
        if verified_transitions % self.config.learn_every != 0:
            return ()
        promoted: list[str] = []
        for child_id, parents in self.TARGETS.items():
            try:
                proposal = self.causal_model.kernel.learn_mechanism(child_id, parents, minimum_samples=self.config.minimum_verified_transitions)
                mechanism = self.causal_model.kernel.promote_mechanism(
                    proposal,
                    minimum_confidence=self.config.minimum_mechanism_confidence,
                    maximum_heldout_log_loss=self.config.maximum_heldout_log_loss,
                    drift_guard_bits=self.config.drift_guard_bits,
                )
                self.promoted.add(child_id)
                promoted.append(f"{child_id}:v{mechanism.version}")
            except (CausalEpistemicError, AgentContractError):
                self.failed_promotions[child_id] += 1
        return tuple(promoted)


class CausalSupervisor:
    """Safe policy-improvement facade over ``LiveSupervisor``.

    The baseline is always evaluated first.  A causal recommendation can only
    replace a soft baseline action.  Safety-critical baseline actions are an
    immutable boundary and are returned verbatim.
    """

    HARD_BASELINE = frozenset({
        InterventionKind.ABORT_RUN,
        InterventionKind.REQUEST_CONFIRMATION,
        InterventionKind.ABORT_OPTION,
    })

    SOFT_KINDS = (
        InterventionKind.CONTINUE,
        InterventionKind.REDIRECT,
        InterventionKind.REPLAN,
        InterventionKind.SEEK_INFORMATION,
        InterventionKind.VERIFY,
        InterventionKind.SUSPEND_INTENTION,
        InterventionKind.SWITCH_INTENTION,
    )

    def __init__(
        self,
        baseline: LiveSupervisor | None = None,
        *,
        config: CausalControlConfig | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.baseline = baseline or LiveSupervisor(clock=clock)
        self.config = config or CausalControlConfig()
        self.encoder = SupervisorStateEncoder()
        self.causal = SupervisorCausalModel()
        self.learner = CausalSupervisorLearner(self.causal, self.config)
        self._clock = clock
        self._pending: dict[str, tuple[EncodedSupervisorState, Intervention]] = {}
        self._support: Counter[str] = Counter()
        self._transitions: deque[CausalControlTransition] = deque(maxlen=self.config.history_limit)
        self._assessments: deque[CausalSupervisorAssessment] = deque(maxlen=self.config.history_limit)
        self._lock = threading.RLock()

    def evaluate(self, signals: SupervisorSignals) -> Intervention:
        baseline = self.baseline.evaluate(signals)
        state = self.encoder.encode(signals)
        with self._lock:
            self._pending[signals.run_id] = (state, baseline)
        assessment = self.assess(signals, baseline=baseline, state=state)
        with self._lock:
            self._assessments.append(assessment)
        if not assessment.override_allowed or assessment.recommended_kind == baseline.kind:
            return baseline
        return self._override(baseline, assessment)

    def observe_next(self, signals: SupervisorSignals, *, verified: bool) -> CausalControlTransition | None:
        after = self.encoder.encode(signals)
        with self._lock:
            pending = self._pending.pop(signals.run_id, None)
        if pending is None:
            return None
        before, intervention = pending
        outcome, trend, reward = self.encoder.classify_outcome(before, after, verified=verified)
        transition_id = stable_id("control-transition", {"run": signals.run_id, "before": before.fingerprint, "action": intervention.kind.value, "after": after.fingerprint})
        sample = TransitionSample(
            sample_id=stable_id("causal-sample", {"transition": transition_id}),
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
            metadata={"trend": trend.value, "reward": reward, "baseline_intervention_id": intervention.intervention_id},
        )
        self.causal.kernel.record_transition(sample)
        if verified:
            self._support[intervention.kind.value] += 1
        record = CausalControlTransition(
            transition_id=transition_id,
            run_id=signals.run_id,
            baseline_intervention_id=intervention.intervention_id,
            action_kind=intervention.kind,
            before=before,
            after=after,
            verified=verified,
            outcome=outcome,
            trend=trend,
            reward=reward,
            sample_id=sample.sample_id,
            fingerprint=stable_fingerprint({"transition": transition_id, "sample": sample.sample_id, "verified": verified, "outcome": outcome.value, "reward": reward}),
        )
        with self._lock:
            self._transitions.append(record)
            verified_count = sum(1 for item in self._transitions if item.verified)
        self.learner.maybe_learn(verified_count)
        return record

    def assess(
        self,
        signals: SupervisorSignals,
        *,
        baseline: Intervention | None = None,
        state: EncodedSupervisorState | None = None,
    ) -> CausalSupervisorAssessment:
        baseline = baseline or self.baseline.evaluate(signals)
        state = state or self.encoder.encode(signals)
        reasons: list[str] = []
        verified_count = sum(1 for item in self._transitions if item.verified)
        if baseline.kind in self.HARD_BASELINE:
            reasons.append("hard baseline intervention is non-overridable")
            return self._assessment(signals, baseline, baseline.kind, None, None, 0.0, False, reasons)
        if not self.config.enable_overrides:
            reasons.append("causal overrides disabled")
            return self._assessment(signals, baseline, baseline.kind, None, None, 0.0, False, reasons)
        if verified_count < self.config.minimum_verified_transitions:
            reasons.append(f"insufficient verified transitions: {verified_count}/{self.config.minimum_verified_transitions}")
            return self._assessment(signals, baseline, baseline.kind, None, None, 0.0, False, reasons)
        if len(self.learner.promoted) < self.config.minimum_promoted_mechanisms:
            reasons.append(f"insufficient promoted mechanisms: {len(self.learner.promoted)}/{self.config.minimum_promoted_mechanisms}")
            return self._assessment(signals, baseline, baseline.kind, None, None, 0.0, False, reasons)

        actions: list[EpistemicAction] = []
        candidate_kinds: list[InterventionKind] = []
        for kind in self.SOFT_KINDS:
            if not self._kind_allowed(kind, baseline, signals):
                continue
            support = self._support[kind.value]
            if kind != baseline.kind and support < self.config.minimum_action_support:
                continue
            candidate_kinds.append(kind)
            actions.append(EpistemicAction(action_id=f"control:{kind.value}", interventions={"control_action": kind.value}, observation_targets=("n_progress", "n_failures", "n_uncertainty", "n_loop", "outcome"), risk=self._kind_risk(kind), reversible=True, base_cost=self._kind_cost(kind)))
        if not actions:
            reasons.append("no supported causal alternative")
            return self._assessment(signals, baseline, baseline.kind, None, None, 0.0, False, reasons)

        evidence = {f"s_{key}": value for key, value in state.values.items()}
        try:
            ranked = self.causal.kernel.recommend(actions, evidence=evidence, maximum_risk=self.config.maximum_override_risk)
        except CausalEpistemicError as exc:
            reasons.append(f"causal inference unavailable: {type(exc).__name__}")
            return self._assessment(signals, baseline, baseline.kind, None, None, 0.0, False, reasons)
        by_kind = {InterventionKind(item.action_id.split(":", 1)[1]): item for item in ranked}
        baseline_eval = by_kind.get(baseline.kind)
        if baseline_eval is None:
            reasons.append("baseline lacked supported causal evaluation")
            return self._assessment(signals, baseline, baseline.kind, None, None, 0.0, False, reasons)
        best = max(ranked, key=lambda item: (item.expected_utility, item.action_id))
        recommended = InterventionKind(best.action_id.split(":", 1)[1])
        gain = best.expected_utility - baseline_eval.expected_utility
        if recommended == baseline.kind:
            reasons.append("causal model agrees with baseline")
            return self._assessment(signals, baseline, recommended, baseline_eval.expected_utility, best.expected_utility, gain, False, reasons)
        if gain < self.config.minimum_override_gain:
            reasons.append(f"expected utility gain {gain:.4f} below margin {self.config.minimum_override_gain:.4f}")
            return self._assessment(signals, baseline, baseline.kind, baseline_eval.expected_utility, best.expected_utility, gain, False, reasons)
        if _RISK_LEVEL[self._kind_risk(recommended)] > _RISK_LEVEL[self._kind_risk(baseline.kind)]:
            reasons.append("causal alternative would increase control risk")
            return self._assessment(signals, baseline, baseline.kind, baseline_eval.expected_utility, best.expected_utility, gain, False, reasons)
        reasons.extend((f"supported causal alternative {recommended.value}", f"expected utility gain={gain:.4f}"))
        return self._assessment(signals, baseline, recommended, baseline_eval.expected_utility, best.expected_utility, gain, True, reasons)

    def _assessment(self, signals: SupervisorSignals, baseline: Intervention, recommended: InterventionKind, baseline_utility: float | None, recommended_utility: float | None, gain: float, override: bool, reasons: Sequence[str]) -> CausalSupervisorAssessment:
        assessment_id = stable_id("causal-supervisor", {"run": signals.run_id, "baseline": baseline.intervention_id, "recommended": recommended.value, "gain": gain, "model": self.causal.kernel.fingerprint})
        support = {kind.value: self._support[kind.value] for kind in InterventionKind if self._support[kind.value]}
        return CausalSupervisorAssessment(
            assessment_id=assessment_id,
            run_id=signals.run_id,
            baseline=baseline,
            recommended_kind=recommended,
            baseline_expected_utility=baseline_utility,
            recommended_expected_utility=recommended_utility,
            expected_gain=gain,
            override_allowed=override,
            support=support,
            promoted_mechanisms=len(self.learner.promoted),
            reasons=tuple(reasons),
            model_fingerprint=self.causal.kernel.fingerprint,
            fingerprint=stable_fingerprint({"assessment": assessment_id, "override": override, "support": support, "reasons": list(reasons)}),
        )

    def _override(self, baseline: Intervention, assessment: CausalSupervisorAssessment) -> Intervention:
        kind = assessment.recommended_kind
        at = self._clock()
        return Intervention(
            intervention_id=stable_id("causal-intervention", {"baseline": baseline.intervention_id, "assessment": assessment.assessment_id, "kind": kind.value}),
            run_id=baseline.run_id,
            kind=kind,
            reason=f"Causal policy improvement over soft baseline: {'; '.join(assessment.reasons)}",
            priority=min(0.94, max(baseline.priority, 0.50 + min(0.40, assessment.expected_gain))),
            created_at=at,
            target_intention_id=baseline.target_intention_id,
            target_option_execution_id=baseline.target_option_execution_id,
            directive=self._directive(kind),
            evidence_ids=baseline.evidence_ids,
            expected_effect=f"Improve next verified checkpoint; estimated utility gain {assessment.expected_gain:.4f}.",
            hard=False,
            metadata={**dict(baseline.metadata), "causal_override": True, "baseline_kind": baseline.kind.value, "baseline_intervention_id": baseline.intervention_id, "assessment_id": assessment.assessment_id, "causal_model_fingerprint": assessment.model_fingerprint},
        )

    def _kind_allowed(self, kind: InterventionKind, baseline: Intervention, signals: SupervisorSignals) -> bool:
        if kind in self.HARD_BASELINE:
            return False
        if _RISK_LEVEL[self._kind_risk(kind)] > _RISK_LEVEL[self.config.maximum_override_risk]:
            return False
        if signals.pending_confirmation and kind is not InterventionKind.REQUEST_CONFIRMATION:
            return False
        if baseline.hard and kind != baseline.kind:
            return False
        return True

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
            InterventionKind.REDIRECT: 0.15,
            InterventionKind.REPLAN: 0.35,
            InterventionKind.SEEK_INFORMATION: 0.25,
            InterventionKind.VERIFY: 0.20,
            InterventionKind.SUSPEND_INTENTION: 0.15,
            InterventionKind.SWITCH_INTENTION: 0.30,
            InterventionKind.PAUSE: 0.10,
            InterventionKind.REQUEST_CONFIRMATION: 0.10,
            InterventionKind.ABORT_OPTION: 0.25,
            InterventionKind.ABORT_RUN: 1.0,
        }[kind]

    @staticmethod
    def _directive(kind: InterventionKind) -> str:
        return {
            InterventionKind.CONTINUE: "Continue the current verified path without adding speculative work.",
            InterventionKind.REDIRECT: "Change tactic while preserving verified completed work and policy constraints.",
            InterventionKind.REPLAN: "Replan from verified state and preserve completed mutations.",
            InterventionKind.SEEK_INFORMATION: "Acquire the lowest-cost discriminating observation before committing further.",
            InterventionKind.VERIFY: "Spend the next control step on independent verification.",
            InterventionKind.SUSPEND_INTENTION: "Suspend the current intention while preserving resumable state.",
            InterventionKind.SWITCH_INTENTION: "Switch to the supported higher-value intention without discarding verified work.",
            InterventionKind.PAUSE: "Pause safely and checkpoint state.",
            InterventionKind.REQUEST_CONFIRMATION: "Request explicit confirmation.",
            InterventionKind.ABORT_OPTION: "Abort the current option safely.",
            InterventionKind.ABORT_RUN: "Abort the run safely.",
        }[kind]

    def transitions(self, *, verified_only: bool = False) -> tuple[CausalControlTransition, ...]:
        with self._lock:
            values = tuple(self._transitions)
        if verified_only:
            values = tuple(item for item in values if item.verified)
        return values

    def assessments(self, *, run_id: str | None = None) -> tuple[CausalSupervisorAssessment, ...]:
        with self._lock:
            values = tuple(self._assessments)
        if run_id is not None:
            run_id = require_id("run_id", run_id)
            values = tuple(item for item in values if item.run_id == run_id)
        return values

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "causal": self.causal.kernel.fingerprint,
            "support": dict(sorted(self._support.items())),
            "promoted": sorted(self.learner.promoted),
            "transitions": [item.fingerprint for item in self._transitions],
            "assessments": [item.fingerprint for item in self._assessments],
        })

    def summary(self) -> dict[str, Any]:
        verified = sum(1 for item in self._transitions if item.verified)
        overrides = sum(1 for item in self._assessments if item.override_allowed)
        return {
            "transitions": len(self._transitions),
            "verified_transitions": verified,
            "support": dict(sorted(self._support.items())),
            "promoted_mechanisms": sorted(self.learner.promoted),
            "failed_promotions": dict(sorted(self.learner.failed_promotions.items())),
            "assessments": len(self._assessments),
            "allowed_overrides": overrides,
            "causal_model": self.causal.kernel.summary(),
            "fingerprint": self.fingerprint,
        }
