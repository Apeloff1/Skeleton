"""Metacognitive control for the Jeeves agent runtime.

The language model proposes content.  The meta-controller decides *what kind of
cognitive operation is justified next* from deterministic run signals:
uncertainty, contradictions, verification state, plan progress, failure streaks,
risk, evidence freshness, budget pressure, action-model reliability, and loop
stagnation.

This is intentionally not a second free-running model.  It is a host-side
control policy with auditable scores, hysteresis, cooldowns, loop detection,
and bounded intervention budgets.  The runtime can ask it whether to retrieve,
reason, verify, replan, answer, request confirmation, or terminate.
"""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .action_model import ContextSignature, SkillLibrary
from .types import (
    AgentContractError,
    AgentPhase,
    Budget,
    Plan,
    RiskTier,
    StepStatus,
    Usage,
    finite_number,
    json_safe,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)
from .world_model import BeliefGraph


class MetaCognitionError(RuntimeError):
    pass


class CognitiveMode(str, Enum):
    PLAN = "plan"
    EXECUTE = "execute"
    RETRIEVE = "retrieve"
    DELIBERATE = "deliberate"
    VERIFY = "verify"
    REPLAN = "replan"
    RESOLVE_CONTRADICTION = "resolve_contradiction"
    SEEK_INFORMATION = "seek_information"
    CONSOLIDATE_MEMORY = "consolidate_memory"
    FINALIZE = "finalize"
    REQUEST_CONFIRMATION = "request_confirmation"
    DEFER = "defer"
    TERMINATE = "terminate"


class MetaReason(str, Enum):
    GOAL_INCOMPLETE = "goal_incomplete"
    HIGH_UNCERTAINTY = "high_uncertainty"
    CONTRADICTION = "contradiction"
    VERIFICATION_REQUIRED = "verification_required"
    PLAN_EXHAUSTED = "plan_exhausted"
    TOOL_FAILURE = "tool_failure"
    FAILURE_STREAK = "failure_streak"
    LOW_SKILL_RELIABILITY = "low_skill_reliability"
    HIGH_RISK = "high_risk"
    LOW_BUDGET = "low_budget"
    STAGNATION = "stagnation"
    LOOP_DETECTED = "loop_detected"
    SUFFICIENT_EVIDENCE = "sufficient_evidence"
    PLAN_COMPLETE = "plan_complete"
    EXPLICIT_CONFIRMATION = "explicit_confirmation"
    INFORMATION_GAIN = "information_gain"
    DEFAULT = "default"


@dataclass(frozen=True, slots=True)
class BudgetPressure:
    steps: float
    model_calls: float
    tool_calls: float
    tokens: float
    wall_clock: float

    def __post_init__(self) -> None:
        for name in ("steps", "model_calls", "tool_calls", "tokens", "wall_clock"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))

    @property
    def maximum(self) -> float:
        return max(self.steps, self.model_calls, self.tool_calls, self.tokens, self.wall_clock)

    @property
    def mean(self) -> float:
        return (self.steps + self.model_calls + self.tool_calls + self.tokens + self.wall_clock) / 5.0

    @property
    def critical(self) -> bool:
        return self.maximum >= 0.92


@dataclass(frozen=True, slots=True)
class ProgressSignals:
    plan_total: int = 0
    plan_completed: int = 0
    plan_failed: int = 0
    plan_blocked: int = 0
    ready_steps: int = 0
    running_steps: int = 0
    successful_verifications: int = 0
    failed_verifications: int = 0
    consecutive_failures: int = 0
    replans: int = 0

    def __post_init__(self) -> None:
        for name in (
            "plan_total",
            "plan_completed",
            "plan_failed",
            "plan_blocked",
            "ready_steps",
            "running_steps",
            "successful_verifications",
            "failed_verifications",
            "consecutive_failures",
            "replans",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")

    @property
    def completion_fraction(self) -> float:
        return self.plan_completed / self.plan_total if self.plan_total else 0.0

    @property
    def terminal_fraction(self) -> float:
        terminal = self.plan_completed + self.plan_failed + self.plan_blocked
        return terminal / self.plan_total if self.plan_total else 0.0

    @property
    def verification_success_rate(self) -> float:
        total = self.successful_verifications + self.failed_verifications
        return self.successful_verifications / total if total else 0.5


@dataclass(frozen=True, slots=True)
class EpistemicSignals:
    belief_count: int = 0
    world_entropy_bits: float = 0.0
    mean_uncertainty: float = 0.0
    maximum_uncertainty: float = 0.0
    contradiction_pressure: float = 0.0
    unresolved_contradictions: int = 0
    expected_information_gain_bits: float = 0.0
    evidence_count: int = 0
    stale_evidence_fraction: float = 0.0
    grounded_claim_fraction: float = 1.0

    def __post_init__(self) -> None:
        for name in ("belief_count", "unresolved_contradictions", "evidence_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")
        for name in ("world_entropy_bits", "expected_information_gain_bits"):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        for name in ("mean_uncertainty", "maximum_uncertainty", "contradiction_pressure", "stale_evidence_fraction", "grounded_claim_fraction"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ActionSignals:
    proposed_skill_id: str | None = None
    empirical_success: float = 0.5
    verification_quality: float = 0.5
    skill_uncertainty: float = 1.0
    failure_streak: int = 0
    fallback_count: int = 0
    context_match: float = 0.0

    def __post_init__(self) -> None:
        if self.proposed_skill_id is not None:
            object.__setattr__(self, "proposed_skill_id", require_id("proposed_skill_id", self.proposed_skill_id))
        for name in ("empirical_success", "verification_quality", "skill_uncertainty", "context_match"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in ("failure_streak", "fallback_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")


@dataclass(frozen=True, slots=True)
class RiskSignals:
    current_risk: RiskTier = RiskTier.READ_ONLY
    confirmation_required: bool = False
    irreversible: bool = False
    external_side_effect: bool = False
    blast_radius: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.current_risk, RiskTier):
            object.__setattr__(self, "current_risk", RiskTier(str(self.current_risk)))
        if not isinstance(self.confirmation_required, bool) or not isinstance(self.irreversible, bool) or not isinstance(self.external_side_effect, bool):
            raise AgentContractError("risk flags must be boolean")
        object.__setattr__(self, "blast_radius", probability("blast_radius", self.blast_radius))


@dataclass(frozen=True, slots=True)
class LoopSignals:
    repeated_state_count: int = 0
    repeated_action_count: int = 0
    unchanged_evidence_cycles: int = 0
    unchanged_plan_cycles: int = 0
    answer_revision_cycles: int = 0

    def __post_init__(self) -> None:
        for name in (
            "repeated_state_count",
            "repeated_action_count",
            "unchanged_evidence_cycles",
            "unchanged_plan_cycles",
            "answer_revision_cycles",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")

    @property
    def severity(self) -> float:
        weighted = (
            self.repeated_state_count * 0.20
            + self.repeated_action_count * 0.20
            + self.unchanged_evidence_cycles * 0.25
            + self.unchanged_plan_cycles * 0.20
            + self.answer_revision_cycles * 0.15
        )
        return max(0.0, min(1.0, weighted / 5.0))


@dataclass(frozen=True, slots=True)
class MetaState:
    run_id: str
    phase: AgentPhase
    budget: BudgetPressure
    progress: ProgressSignals
    epistemic: EpistemicSignals
    action: ActionSignals
    risk: RiskSignals
    loop: LoopSignals
    goal_complete: bool = False
    pending_verification: bool = False
    pending_confirmation: bool = False
    last_mode: CognitiveMode | None = None
    mode_repetition: int = 0
    intervention_count: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        if not isinstance(self.phase, AgentPhase):
            object.__setattr__(self, "phase", AgentPhase(str(self.phase)))
        for name, expected in (
            ("budget", BudgetPressure),
            ("progress", ProgressSignals),
            ("epistemic", EpistemicSignals),
            ("action", ActionSignals),
            ("risk", RiskSignals),
            ("loop", LoopSignals),
        ):
            if not isinstance(getattr(self, name), expected):
                raise AgentContractError(f"{name} must be {expected.__name__}")
        if self.last_mode is not None and not isinstance(self.last_mode, CognitiveMode):
            object.__setattr__(self, "last_mode", CognitiveMode(str(self.last_mode)))
        for name in ("mode_repetition", "intervention_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def state_fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "phase": self.phase.value,
                "budget": self.budget,
                "progress": self.progress,
                "epistemic": self.epistemic,
                "action": self.action,
                "risk": self.risk,
                "loop": self.loop,
                "goal_complete": self.goal_complete,
                "pending_verification": self.pending_verification,
                "pending_confirmation": self.pending_confirmation,
            }
        )


@dataclass(frozen=True, slots=True)
class ModeScore:
    mode: CognitiveMode
    score: float
    reasons: tuple[MetaReason, ...]
    factors: Mapping[str, float] = field(default_factory=dict)
    blocked: bool = False
    block_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, CognitiveMode):
            object.__setattr__(self, "mode", CognitiveMode(str(self.mode)))
        score = finite_number("score", self.score)
        object.__setattr__(self, "score", max(0.0, min(1.0, score)))
        object.__setattr__(self, "reasons", tuple(reason if isinstance(reason, MetaReason) else MetaReason(str(reason)) for reason in self.reasons))
        object.__setattr__(self, "factors", {str(key): finite_number(str(key), value) for key, value in dict(self.factors).items()})
        if self.block_reason is not None:
            object.__setattr__(self, "block_reason", bounded_text("block_reason", self.block_reason, maximum=2048))


@dataclass(frozen=True, slots=True)
class MetaDecision:
    decision_id: str
    run_id: str
    mode: CognitiveMode
    score: float
    reasons: tuple[MetaReason, ...]
    alternatives: tuple[ModeScore, ...]
    state_fingerprint: str
    at: float
    directive: str
    hard_stop: bool = False
    requires_confirmation: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", require_id("decision_id", self.decision_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        if not isinstance(self.mode, CognitiveMode):
            object.__setattr__(self, "mode", CognitiveMode(str(self.mode)))
        object.__setattr__(self, "score", probability("score", self.score))
        object.__setattr__(self, "reasons", tuple(reason if isinstance(reason, MetaReason) else MetaReason(str(reason)) for reason in self.reasons))
        if any(not isinstance(item, ModeScore) for item in self.alternatives):
            raise AgentContractError("alternatives must contain ModeScore")
        object.__setattr__(self, "state_fingerprint", str(self.state_fingerprint).strip().lower())
        at = finite_number("at", self.at)
        if at < 0:
            raise AgentContractError("decision time must be non-negative")
        object.__setattr__(self, "at", at)
        object.__setattr__(self, "directive", bounded_text("directive", self.directive, maximum=4096))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class MetaPolicy:
    high_uncertainty: float = 0.62
    contradiction_threshold: float = 0.45
    information_gain_threshold_bits: float = 0.08
    low_skill_success: float = 0.55
    low_verification_quality: float = 0.60
    failure_streak_replan: int = 2
    loop_severity_replan: float = 0.50
    loop_severity_stop: float = 0.82
    budget_finalize_threshold: float = 0.80
    budget_stop_threshold: float = 0.97
    max_replans: int = 4
    max_interventions: int = 32
    mode_hysteresis: float = 0.08
    max_same_mode_repetition: int = 4

    def __post_init__(self) -> None:
        for name in (
            "high_uncertainty",
            "contradiction_threshold",
            "low_skill_success",
            "low_verification_quality",
            "loop_severity_replan",
            "loop_severity_stop",
            "budget_finalize_threshold",
            "budget_stop_threshold",
            "mode_hysteresis",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        gain = finite_number("information_gain_threshold_bits", self.information_gain_threshold_bits)
        if gain < 0:
            raise AgentContractError("information_gain_threshold_bits must be non-negative")
        object.__setattr__(self, "information_gain_threshold_bits", gain)
        for name in ("failure_streak_replan", "max_replans", "max_interventions", "max_same_mode_repetition"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AgentContractError(f"{name} must be positive integer")
        if self.loop_severity_stop < self.loop_severity_replan:
            raise AgentContractError("loop stop threshold must be >= replan threshold")
        if self.budget_stop_threshold < self.budget_finalize_threshold:
            raise AgentContractError("budget stop threshold must be >= finalize threshold")


class LoopDetector:
    """Detect repeated cognitive states/actions and evidence-free churn."""

    def __init__(self, *, window: int = 24) -> None:
        if isinstance(window, bool) or not isinstance(window, int) or window < 4:
            raise ValueError("loop detector window must be >= 4")
        self.window = window
        self._states: deque[str] = deque(maxlen=window)
        self._actions: deque[str] = deque(maxlen=window)
        self._evidence: deque[str] = deque(maxlen=window)
        self._plans: deque[str] = deque(maxlen=window)
        self._answers: deque[str] = deque(maxlen=window)
        self._lock = threading.RLock()

    def observe(
        self,
        *,
        state_fingerprint: str,
        action_fingerprint: str | None = None,
        evidence_fingerprint: str | None = None,
        plan_fingerprint: str | None = None,
        answer_fingerprint: str | None = None,
    ) -> LoopSignals:
        with self._lock:
            self._states.append(str(state_fingerprint))
            if action_fingerprint is not None:
                self._actions.append(str(action_fingerprint))
            if evidence_fingerprint is not None:
                self._evidence.append(str(evidence_fingerprint))
            if plan_fingerprint is not None:
                self._plans.append(str(plan_fingerprint))
            if answer_fingerprint is not None:
                self._answers.append(str(answer_fingerprint))
            return LoopSignals(
                repeated_state_count=self._tail_repeat_count(self._states),
                repeated_action_count=self._tail_repeat_count(self._actions),
                unchanged_evidence_cycles=self._tail_repeat_count(self._evidence),
                unchanged_plan_cycles=self._tail_repeat_count(self._plans),
                answer_revision_cycles=self._cycle_count(self._answers),
            )

    @staticmethod
    def _tail_repeat_count(values: Sequence[str]) -> int:
        if not values:
            return 0
        last = values[-1]
        count = 0
        for value in reversed(values):
            if value != last:
                break
            count += 1
        return max(0, count - 1)

    @staticmethod
    def _cycle_count(values: Sequence[str]) -> int:
        if len(values) < 4:
            return 0
        last = values[-1]
        count = 0
        for index in range(len(values) - 2, -1, -1):
            if values[index] == last:
                count += 1
        return count


class MetaController:
    """Deterministic cognitive-mode selector with auditable scoring."""

    _RISK_LEVEL = {
        RiskTier.READ_ONLY: 0.05,
        RiskTier.REVERSIBLE: 0.20,
        RiskTier.MUTATING: 0.50,
        RiskTier.EXTERNAL: 0.70,
        RiskTier.HIGH_IMPACT: 1.00,
    }

    def __init__(
        self,
        *,
        policy: MetaPolicy | None = None,
        clock: Callable[[], float] = time.time,
        history_limit: int = 512,
    ) -> None:
        self.policy = policy or MetaPolicy()
        self._clock = clock
        self._history: deque[MetaDecision] = deque(maxlen=history_limit)
        self._mode_counts: Counter[CognitiveMode] = Counter()
        self._last_by_run: dict[str, MetaDecision] = {}
        self._lock = threading.RLock()

    def decide(self, state: MetaState) -> MetaDecision:
        if not isinstance(state, MetaState):
            raise TypeError("state must be MetaState")
        scores = self._score_modes(state)
        viable = [item for item in scores if not item.blocked]
        if not viable:
            viable = [ModeScore(CognitiveMode.TERMINATE, 1.0, (MetaReason.DEFAULT,), {}, False)]
        viable.sort(key=lambda item: (item.score, self._mode_priority(item.mode)), reverse=True)
        chosen = viable[0]
        chosen = self._apply_hysteresis(state, chosen, viable)
        directive = self._directive(chosen.mode, state, chosen.reasons)
        hard_stop = chosen.mode is CognitiveMode.TERMINATE
        requires_confirmation = chosen.mode is CognitiveMode.REQUEST_CONFIRMATION
        at = self._clock()
        decision = MetaDecision(
            decision_id=stable_id(
                "meta",
                {
                    "run": state.run_id,
                    "state": state.state_fingerprint,
                    "mode": chosen.mode.value,
                    "time": at,
                    "count": len(self._history),
                },
            ),
            run_id=state.run_id,
            mode=chosen.mode,
            score=chosen.score,
            reasons=chosen.reasons,
            alternatives=tuple(viable[:8]),
            state_fingerprint=state.state_fingerprint,
            at=at,
            directive=directive,
            hard_stop=hard_stop,
            requires_confirmation=requires_confirmation,
            metadata={
                "budget_max": state.budget.maximum,
                "loop_severity": state.loop.severity,
                "progress": state.progress.completion_fraction,
                "world_uncertainty": state.epistemic.mean_uncertainty,
            },
        )
        with self._lock:
            self._history.append(decision)
            self._mode_counts[decision.mode] += 1
            self._last_by_run[state.run_id] = decision
        return decision

    def history(self, *, run_id: str | None = None) -> tuple[MetaDecision, ...]:
        with self._lock:
            values = list(self._history)
        if run_id is not None:
            run_id = require_id("run_id", run_id)
            values = [item for item in values if item.run_id == run_id]
        return tuple(values)

    def last(self, run_id: str) -> MetaDecision | None:
        with self._lock:
            return self._last_by_run.get(require_id("run_id", run_id))

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "decisions": len(self._history),
                "modes": {mode.value: count for mode, count in sorted(self._mode_counts.items(), key=lambda item: item[0].value)},
                "fingerprint": stable_fingerprint(
                    [(item.decision_id, item.run_id, item.mode.value, item.score, item.state_fingerprint) for item in self._history]
                ),
            }

    def _score_modes(self, state: MetaState) -> list[ModeScore]:
        scores: list[ModeScore] = []
        policy = self.policy
        budget = state.budget
        epistemic = state.epistemic
        progress = state.progress
        action = state.action
        loop = state.loop
        risk_level = self._RISK_LEVEL[state.risk.current_risk]

        if state.intervention_count >= policy.max_interventions:
            scores.append(
                ModeScore(
                    CognitiveMode.TERMINATE,
                    1.0,
                    (MetaReason.LOW_BUDGET, MetaReason.STAGNATION),
                    {"interventions": 1.0},
                )
            )
            return scores

        terminate_score = 0.0
        terminate_reasons: list[MetaReason] = []
        if budget.maximum >= policy.budget_stop_threshold:
            terminate_score = max(terminate_score, 0.90 + 0.10 * budget.maximum)
            terminate_reasons.append(MetaReason.LOW_BUDGET)
        if loop.severity >= policy.loop_severity_stop:
            terminate_score = max(terminate_score, 0.88 + 0.12 * loop.severity)
            terminate_reasons.append(MetaReason.LOOP_DETECTED)
        if progress.replans >= policy.max_replans and progress.consecutive_failures >= policy.failure_streak_replan:
            terminate_score = max(terminate_score, 0.86)
            terminate_reasons.extend((MetaReason.PLAN_EXHAUSTED, MetaReason.FAILURE_STREAK))
        scores.append(ModeScore(CognitiveMode.TERMINATE, terminate_score, tuple(dict.fromkeys(terminate_reasons)) or (MetaReason.DEFAULT,), {"budget": budget.maximum, "loop": loop.severity}))

        if state.pending_confirmation or state.risk.confirmation_required:
            scores.append(
                ModeScore(
                    CognitiveMode.REQUEST_CONFIRMATION,
                    0.99,
                    (MetaReason.EXPLICIT_CONFIRMATION, MetaReason.HIGH_RISK),
                    {"risk": risk_level, "blast_radius": state.risk.blast_radius},
                )
            )
        else:
            scores.append(ModeScore(CognitiveMode.REQUEST_CONFIRMATION, 0.0, (MetaReason.DEFAULT,), {}, True, "no pending confirmation"))

        if state.goal_complete and not state.pending_verification:
            finalize_score = 0.96
            if epistemic.grounded_claim_fraction < 1.0:
                finalize_score *= epistemic.grounded_claim_fraction
            if epistemic.unresolved_contradictions:
                finalize_score *= max(0.2, 1.0 - epistemic.contradiction_pressure)
            scores.append(ModeScore(CognitiveMode.FINALIZE, finalize_score, (MetaReason.PLAN_COMPLETE, MetaReason.SUFFICIENT_EVIDENCE), {"grounded": epistemic.grounded_claim_fraction}))
        else:
            finalize_pressure = max(0.0, (budget.maximum - policy.budget_finalize_threshold) / max(1e-9, 1.0 - policy.budget_finalize_threshold))
            scores.append(ModeScore(CognitiveMode.FINALIZE, finalize_pressure * 0.82, (MetaReason.LOW_BUDGET,), {"budget": budget.maximum}))

        if state.pending_verification:
            score = 0.98
            if risk_level >= 0.5:
                score = 1.0
            scores.append(ModeScore(CognitiveMode.VERIFY, score, (MetaReason.VERIFICATION_REQUIRED, MetaReason.HIGH_RISK if risk_level >= 0.5 else MetaReason.DEFAULT), {"risk": risk_level}))
        else:
            verification_need = (1.0 - progress.verification_success_rate) * 0.30 + risk_level * 0.25
            scores.append(ModeScore(CognitiveMode.VERIFY, verification_need, (MetaReason.VERIFICATION_REQUIRED,), {"historical_failure": 1.0 - progress.verification_success_rate, "risk": risk_level}))

        contradiction_score = epistemic.contradiction_pressure * 0.70 + min(1.0, epistemic.unresolved_contradictions / 3.0) * 0.30
        scores.append(
            ModeScore(
                CognitiveMode.RESOLVE_CONTRADICTION,
                contradiction_score if contradiction_score >= policy.contradiction_threshold else contradiction_score * 0.7,
                (MetaReason.CONTRADICTION,),
                {"pressure": epistemic.contradiction_pressure, "count": min(1.0, epistemic.unresolved_contradictions / 5.0)},
                blocked=epistemic.unresolved_contradictions == 0,
                block_reason="no unresolved contradictions" if epistemic.unresolved_contradictions == 0 else None,
            )
        )

        info_gain = min(1.0, epistemic.expected_information_gain_bits / max(0.001, policy.information_gain_threshold_bits * 4.0))
        seek_score = epistemic.mean_uncertainty * 0.45 + epistemic.maximum_uncertainty * 0.20 + info_gain * 0.35
        if budget.maximum >= 0.90:
            seek_score *= 0.35
        scores.append(
            ModeScore(
                CognitiveMode.SEEK_INFORMATION,
                seek_score,
                (MetaReason.HIGH_UNCERTAINTY, MetaReason.INFORMATION_GAIN),
                {"mean_uncertainty": epistemic.mean_uncertainty, "max_uncertainty": epistemic.maximum_uncertainty, "information_gain": info_gain},
                blocked=epistemic.expected_information_gain_bits < policy.information_gain_threshold_bits and epistemic.mean_uncertainty < policy.high_uncertainty,
                block_reason="uncertainty/information gain below thresholds",
            )
        )

        retrieve_score = epistemic.mean_uncertainty * 0.35 + epistemic.stale_evidence_fraction * 0.35 + (1.0 - epistemic.grounded_claim_fraction) * 0.30
        if epistemic.evidence_count == 0:
            retrieve_score = max(retrieve_score, 0.78)
        if budget.tool_calls >= 0.90:
            retrieve_score *= 0.25
        scores.append(ModeScore(CognitiveMode.RETRIEVE, retrieve_score, (MetaReason.HIGH_UNCERTAINTY,), {"stale": epistemic.stale_evidence_fraction, "evidence_empty": 1.0 if epistemic.evidence_count == 0 else 0.0}))

        deliberate_score = epistemic.mean_uncertainty * 0.30 + (1.0 - action.context_match) * 0.15 + (1.0 - progress.completion_fraction) * 0.20 + action.skill_uncertainty * 0.20 + loop.severity * 0.15
        if budget.model_calls >= 0.90 or budget.tokens >= 0.90:
            deliberate_score *= 0.30
        scores.append(ModeScore(CognitiveMode.DELIBERATE, deliberate_score, (MetaReason.GOAL_INCOMPLETE,), {"uncertainty": epistemic.mean_uncertainty, "skill_uncertainty": action.skill_uncertainty}))

        replan_score = 0.0
        replan_reasons: list[MetaReason] = []
        if progress.consecutive_failures >= policy.failure_streak_replan:
            replan_score += min(0.55, progress.consecutive_failures * 0.16)
            replan_reasons.append(MetaReason.FAILURE_STREAK)
        if action.failure_streak >= policy.failure_streak_replan:
            replan_score += min(0.30, action.failure_streak * 0.10)
            replan_reasons.append(MetaReason.TOOL_FAILURE)
        if action.empirical_success < policy.low_skill_success:
            replan_score += (policy.low_skill_success - action.empirical_success) * 0.50
            replan_reasons.append(MetaReason.LOW_SKILL_RELIABILITY)
        if loop.severity >= policy.loop_severity_replan:
            replan_score += loop.severity * 0.35
            replan_reasons.append(MetaReason.STAGNATION)
        if progress.plan_failed or progress.plan_blocked:
            replan_score += min(0.40, (progress.plan_failed + progress.plan_blocked) * 0.12)
            replan_reasons.append(MetaReason.PLAN_EXHAUSTED)
        if progress.replans >= policy.max_replans:
            scores.append(ModeScore(CognitiveMode.REPLAN, 0.0, tuple(replan_reasons) or (MetaReason.DEFAULT,), {}, True, "replan budget exhausted"))
        else:
            scores.append(ModeScore(CognitiveMode.REPLAN, min(1.0, replan_score), tuple(dict.fromkeys(replan_reasons)) or (MetaReason.DEFAULT,), {"failures": min(1.0, progress.consecutive_failures / 5.0), "loop": loop.severity}))

        if state.phase is AgentPhase.CREATED or (progress.plan_total == 0 and not state.goal_complete):
            plan_score = 0.95
        else:
            plan_score = max(0.0, 0.30 - progress.completion_fraction * 0.20)
        scores.append(ModeScore(CognitiveMode.PLAN, plan_score, (MetaReason.GOAL_INCOMPLETE,), {"has_plan": 1.0 if progress.plan_total else 0.0}))

        execute_score = 0.0
        if progress.ready_steps > 0 and not state.pending_verification and not state.pending_confirmation:
            execute_score = 0.50 + min(0.30, progress.ready_steps * 0.05)
            execute_score += action.empirical_success * 0.15
            execute_score += action.verification_quality * 0.05
            execute_score -= risk_level * 0.10
        scores.append(
            ModeScore(
                CognitiveMode.EXECUTE,
                max(0.0, min(1.0, execute_score)),
                (MetaReason.GOAL_INCOMPLETE,),
                {"ready": min(1.0, progress.ready_steps / 5.0), "skill_success": action.empirical_success, "risk": risk_level},
                blocked=progress.ready_steps == 0 or state.pending_verification or state.pending_confirmation,
                block_reason="no executable step or verification/confirmation pending" if progress.ready_steps == 0 or state.pending_verification or state.pending_confirmation else None,
            )
        )

        consolidate_score = 0.08 + min(0.22, progress.plan_completed * 0.02)
        if state.goal_complete:
            consolidate_score += 0.25
        if budget.maximum >= 0.88:
            consolidate_score *= 0.25
        scores.append(ModeScore(CognitiveMode.CONSOLIDATE_MEMORY, consolidate_score, (MetaReason.SUFFICIENT_EVIDENCE,), {"completed": progress.completion_fraction}))

        defer_score = 0.05
        if risk_level >= 0.7 and action.empirical_success < 0.5:
            defer_score = 0.75
        scores.append(ModeScore(CognitiveMode.DEFER, defer_score, (MetaReason.HIGH_RISK, MetaReason.LOW_SKILL_RELIABILITY), {"risk": risk_level, "skill_success": action.empirical_success}))
        return scores

    def _apply_hysteresis(self, state: MetaState, chosen: ModeScore, viable: Sequence[ModeScore]) -> ModeScore:
        if state.last_mode is None or state.last_mode == chosen.mode:
            if state.last_mode == chosen.mode and state.mode_repetition >= self.policy.max_same_mode_repetition:
                alternatives = [item for item in viable if item.mode != chosen.mode and item.score >= chosen.score - 0.20]
                if alternatives:
                    return alternatives[0]
            return chosen
        prior = next((item for item in viable if item.mode == state.last_mode), None)
        if prior is None:
            return chosen
        if prior.score + self.policy.mode_hysteresis >= chosen.score and state.mode_repetition < self.policy.max_same_mode_repetition:
            return prior
        return chosen

    @staticmethod
    def _mode_priority(mode: CognitiveMode) -> int:
        order = {
            CognitiveMode.REQUEST_CONFIRMATION: 100,
            CognitiveMode.TERMINATE: 95,
            CognitiveMode.VERIFY: 90,
            CognitiveMode.RESOLVE_CONTRADICTION: 85,
            CognitiveMode.REPLAN: 80,
            CognitiveMode.SEEK_INFORMATION: 75,
            CognitiveMode.RETRIEVE: 70,
            CognitiveMode.FINALIZE: 65,
            CognitiveMode.EXECUTE: 60,
            CognitiveMode.PLAN: 55,
            CognitiveMode.DELIBERATE: 50,
            CognitiveMode.CONSOLIDATE_MEMORY: 40,
            CognitiveMode.DEFER: 30,
        }
        return order[mode]

    @staticmethod
    def _directive(mode: CognitiveMode, state: MetaState, reasons: Sequence[MetaReason]) -> str:
        reason_text = ", ".join(reason.value for reason in reasons)
        directives = {
            CognitiveMode.PLAN: "Construct or repair a bounded dependency-aware plan before taking action.",
            CognitiveMode.EXECUTE: "Execute the highest-priority ready step under capability and risk policy.",
            CognitiveMode.RETRIEVE: "Acquire fresh external evidence targeted at the least-grounded required claims.",
            CognitiveMode.DELIBERATE: "Perform bounded reasoning over existing evidence; do not mutate external state.",
            CognitiveMode.VERIFY: "Verify the latest action or claim using host-side predicates and independent evidence.",
            CognitiveMode.REPLAN: "Revise the plan around observed failures while preserving verified completed work.",
            CognitiveMode.RESOLVE_CONTRADICTION: "Target contradictory beliefs with discriminating evidence before finalizing.",
            CognitiveMode.SEEK_INFORMATION: "Choose the observation with highest expected information gain per unit cost/risk.",
            CognitiveMode.CONSOLIDATE_MEMORY: "Stage durable memory candidates from verified repeated evidence; do not auto-promote.",
            CognitiveMode.FINALIZE: "Produce a grounded answer restricted to verified evidence and accepted claims.",
            CognitiveMode.REQUEST_CONFIRMATION: "Pause external mutation and request explicit confirmation for the pending capability.",
            CognitiveMode.DEFER: "Do not take the proposed action; surface uncertainty, risk, or missing capability.",
            CognitiveMode.TERMINATE: "Stop the run safely and preserve checkpoint/evidence/trace state for inspection or resume.",
        }
        return f"{directives[mode]} Trigger: {reason_text}."


def budget_pressure(usage: Usage, budget: Budget, *, elapsed_seconds: float) -> BudgetPressure:
    if not isinstance(usage, Usage) or not isinstance(budget, Budget):
        raise TypeError("usage and budget must be typed contracts")
    elapsed = max(0.0, finite_number("elapsed_seconds", elapsed_seconds))
    return BudgetPressure(
        steps=min(1.0, usage.steps / budget.max_steps),
        model_calls=min(1.0, usage.model_calls / budget.max_model_calls),
        tool_calls=min(1.0, usage.tool_calls / budget.max_tool_calls),
        tokens=min(1.0, usage.total_tokens / budget.max_tokens),
        wall_clock=min(1.0, elapsed / budget.max_wall_seconds),
    )


def progress_signals(plan: Plan | None, *, successful_verifications: int = 0, failed_verifications: int = 0, consecutive_failures: int = 0, replans: int = 0) -> ProgressSignals:
    if plan is None:
        return ProgressSignals(
            successful_verifications=successful_verifications,
            failed_verifications=failed_verifications,
            consecutive_failures=consecutive_failures,
            replans=replans,
        )
    statuses = Counter(step.status for step in plan.steps)
    return ProgressSignals(
        plan_total=len(plan.steps),
        plan_completed=statuses[StepStatus.SUCCEEDED] + statuses[StepStatus.SKIPPED],
        plan_failed=statuses[StepStatus.FAILED],
        plan_blocked=statuses[StepStatus.BLOCKED],
        ready_steps=statuses[StepStatus.READY] + sum(
            1
            for step in plan.steps
            if step.status is StepStatus.PENDING and all(plan.step(dep).status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED} for dep in step.dependencies)
        ),
        running_steps=statuses[StepStatus.RUNNING],
        successful_verifications=successful_verifications,
        failed_verifications=failed_verifications,
        consecutive_failures=consecutive_failures,
        replans=replans,
    )


def epistemic_signals(
    graph: BeliefGraph | None,
    *,
    evidence_count: int = 0,
    stale_evidence_fraction: float = 0.0,
    grounded_claim_fraction: float = 1.0,
) -> EpistemicSignals:
    if graph is None:
        return EpistemicSignals(
            evidence_count=evidence_count,
            stale_evidence_fraction=stale_evidence_fraction,
            grounded_claim_fraction=grounded_claim_fraction,
        )
    beliefs = graph.beliefs()
    uncertainties = [belief.uncertainty for belief in beliefs]
    pressure = max((graph.contradiction_pressure(belief.proposition_id) for belief in beliefs), default=0.0)
    unresolved = sum(1 for belief in beliefs if graph.contradiction_pressure(belief.proposition_id) >= 0.45)
    probes = graph.ranked_probes(limit=1, minimum_entropy_bits=0.0)
    expected_gain = probes[0].expected_information_gain_bits if probes else 0.0
    return EpistemicSignals(
        belief_count=len(beliefs),
        world_entropy_bits=graph.world_entropy_bits(),
        mean_uncertainty=sum(uncertainties) / len(uncertainties) if uncertainties else 0.0,
        maximum_uncertainty=max(uncertainties, default=0.0),
        contradiction_pressure=pressure,
        unresolved_contradictions=unresolved,
        expected_information_gain_bits=expected_gain,
        evidence_count=evidence_count,
        stale_evidence_fraction=stale_evidence_fraction,
        grounded_claim_fraction=grounded_claim_fraction,
    )


def action_signals(
    library: SkillLibrary | None,
    *,
    skill_id: str | None = None,
    context: ContextSignature | None = None,
) -> ActionSignals:
    if library is None or skill_id is None:
        return ActionSignals()
    profile = library.profile(skill_id)
    if profile is None:
        return ActionSignals(proposed_skill_id=skill_id)
    fallbacks = library.recommend_fallbacks(skill_id, context=context, limit=4)
    context_match = 0.0
    if context is not None:
        selection = library.select(required_capabilities=profile.spec.capabilities, context=context, top_k=8)
        matched = next((item for item in selection.alternatives if item.skill_id == skill_id), None)
        context_match = matched.context_match if matched is not None else 0.0
    return ActionSignals(
        proposed_skill_id=skill_id,
        empirical_success=profile.empirical_success,
        verification_quality=profile.verification_quality,
        skill_uncertainty=profile.uncertainty,
        failure_streak=profile.failure_streak,
        fallback_count=len(fallbacks),
        context_match=context_match,
    )


@dataclass(slots=True)
class MetaStateBuilder:
    """Convenience accumulator for runtimes that do not want to construct MetaState manually."""

    run_id: str
    phase: AgentPhase = AgentPhase.CREATED
    usage: Usage = field(default_factory=Usage)
    budget_contract: Budget = field(default_factory=Budget)
    started_at: float = field(default_factory=time.monotonic)
    plan: Plan | None = None
    world: BeliefGraph | None = None
    skill_library: SkillLibrary | None = None
    skill_id: str | None = None
    context: ContextSignature | None = None
    risk: RiskSignals = field(default_factory=RiskSignals)
    loop: LoopSignals = field(default_factory=LoopSignals)
    goal_complete: bool = False
    pending_verification: bool = False
    pending_confirmation: bool = False
    successful_verifications: int = 0
    failed_verifications: int = 0
    consecutive_failures: int = 0
    replans: int = 0
    evidence_count: int = 0
    stale_evidence_fraction: float = 0.0
    grounded_claim_fraction: float = 1.0
    last_mode: CognitiveMode | None = None
    mode_repetition: int = 0
    intervention_count: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def build(self, *, now_monotonic: float | None = None) -> MetaState:
        now = time.monotonic() if now_monotonic is None else finite_number("now_monotonic", now_monotonic)
        elapsed = max(0.0, now - self.started_at)
        return MetaState(
            run_id=self.run_id,
            phase=self.phase,
            budget=budget_pressure(self.usage, self.budget_contract, elapsed_seconds=elapsed),
            progress=progress_signals(
                self.plan,
                successful_verifications=self.successful_verifications,
                failed_verifications=self.failed_verifications,
                consecutive_failures=self.consecutive_failures,
                replans=self.replans,
            ),
            epistemic=epistemic_signals(
                self.world,
                evidence_count=self.evidence_count,
                stale_evidence_fraction=self.stale_evidence_fraction,
                grounded_claim_fraction=self.grounded_claim_fraction,
            ),
            action=action_signals(self.skill_library, skill_id=self.skill_id, context=self.context),
            risk=self.risk,
            loop=self.loop,
            goal_complete=self.goal_complete,
            pending_verification=self.pending_verification,
            pending_confirmation=self.pending_confirmation,
            last_mode=self.last_mode,
            mode_repetition=self.mode_repetition,
            intervention_count=self.intervention_count,
            metadata=self.metadata,
        )
