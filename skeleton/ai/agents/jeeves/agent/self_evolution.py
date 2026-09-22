"""Guarded self-evolution for Jeeves.

This module enables continual improvement without live autonomous self-mutation.
Changes to context, skills, routing, planning heuristics, and verifier policy are
represented as explicit proposals with provenance.  Proposals must survive
holdout evaluation, regression floors, canary exposure, and rollback checks
before becoming active.

The system intentionally updates *token-space/runtime policy state*, not model
weights.  It is designed around a simple rule: experience may propose a better
policy, but the currently-running policy is never allowed to declare its own
replacement successful without independent evidence.
"""

from __future__ import annotations

import math
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence

from .trajectory_learning import LessonCandidate, Trajectory
from .types import (
    AgentContractError,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class EvolutionError(RuntimeError):
    pass


class EvolutionTarget(str, Enum):
    CONTEXT = "context"
    SKILL = "skill"
    ROUTING = "routing"
    PLANNING = "planning"
    DELIBERATION = "deliberation"
    VERIFIER = "verifier"
    MEMORY_POLICY = "memory_policy"
    TOOL_POLICY = "tool_policy"


class ProposalStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    REJECTED = "rejected"
    CANARY = "canary"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    SUPERSEDED = "superseded"


class MetricDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


@dataclass(frozen=True, slots=True)
class EvolutionPatch:
    target: EvolutionTarget
    path: str
    before_fingerprint: str
    after_payload: Any
    description: str
    reversible: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.target, EvolutionTarget):
            object.__setattr__(self, "target", EvolutionTarget(str(self.target)))
        object.__setattr__(self, "path", require_id("path", self.path))
        before = str(self.before_fingerprint).strip().lower()
        if len(before) < 16:
            raise AgentContractError("before_fingerprint too short")
        object.__setattr__(self, "before_fingerprint", before)
        object.__setattr__(self, "after_payload", json_safe(self.after_payload))
        object.__setattr__(self, "description", bounded_text("patch description", self.description, maximum=8192))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def after_fingerprint(self) -> str:
        return stable_fingerprint(self.after_payload)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "target": self.target.value,
                "path": self.path,
                "before": self.before_fingerprint,
                "after": self.after_fingerprint,
                "description": self.description,
                "reversible": self.reversible,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True, slots=True)
class EvolutionProposal:
    proposal_id: str
    parent_revision_id: str
    patches: tuple[EvolutionPatch, ...]
    hypothesis: str
    support_trajectory_ids: tuple[str, ...]
    support_lesson_ids: tuple[str, ...]
    confidence: float
    created_at: float = field(default_factory=time.time)
    status: ProposalStatus = ProposalStatus.DRAFT
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", require_id("proposal_id", self.proposal_id))
        object.__setattr__(self, "parent_revision_id", require_id("parent_revision_id", self.parent_revision_id))
        patches = tuple(self.patches)
        if not patches or any(not isinstance(patch, EvolutionPatch) for patch in patches):
            raise AgentContractError("proposal requires EvolutionPatch values")
        keys = [(patch.target, patch.path) for patch in patches]
        if len(set(keys)) != len(keys):
            raise AgentContractError("proposal contains duplicate patch target/path")
        object.__setattr__(self, "patches", patches)
        object.__setattr__(self, "hypothesis", bounded_text("hypothesis", self.hypothesis, maximum=8192))
        object.__setattr__(self, "support_trajectory_ids", tuple(sorted(set(require_id("trajectory_id", value) for value in self.support_trajectory_ids))))
        object.__setattr__(self, "support_lesson_ids", tuple(sorted(set(require_id("lesson_id", value) for value in self.support_lesson_ids))))
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        created = finite_number("created_at", self.created_at)
        if created < 0:
            raise AgentContractError("created_at must be non-negative")
        object.__setattr__(self, "created_at", created)
        if not isinstance(self.status, ProposalStatus):
            object.__setattr__(self, "status", ProposalStatus(str(self.status)))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "parent": self.parent_revision_id,
                "patches": [(patch.target.value, patch.path, patch.fingerprint) for patch in self.patches],
                "hypothesis": self.hypothesis,
                "trajectories": self.support_trajectory_ids,
                "lessons": self.support_lesson_ids,
                "confidence": self.confidence,
            }
        )


@dataclass(frozen=True, slots=True)
class MetricSpec:
    name: str
    direction: MetricDirection
    weight: float = 1.0
    floor: float | None = None
    maximum_regression: float = 0.0
    critical: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_id("metric name", self.name))
        if not isinstance(self.direction, MetricDirection):
            object.__setattr__(self, "direction", MetricDirection(str(self.direction)))
        weight = finite_number("weight", self.weight)
        if weight <= 0:
            raise AgentContractError("metric weight must be positive")
        object.__setattr__(self, "weight", weight)
        if self.floor is not None:
            object.__setattr__(self, "floor", finite_number("floor", self.floor))
        regression = finite_number("maximum_regression", self.maximum_regression)
        if regression < 0:
            raise AgentContractError("maximum_regression must be non-negative")
        object.__setattr__(self, "maximum_regression", regression)


@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    case_id: str
    metrics: Mapping[str, float]
    success: bool
    cost: float = 0.0
    latency_ms: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", require_id("case_id", self.case_id))
        object.__setattr__(self, "metrics", {require_id("metric name", key): finite_number(key, value) for key, value in dict(self.metrics).items()})
        if not isinstance(self.success, bool):
            raise AgentContractError("success must be boolean")
        cost = finite_number("cost", self.cost)
        latency = finite_number("latency_ms", self.latency_ms)
        if cost < 0 or latency < 0:
            raise AgentContractError("cost/latency must be non-negative")
        object.__setattr__(self, "cost", cost)
        object.__setattr__(self, "latency_ms", latency)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class PairedMetricResult:
    metric: str
    baseline_mean: float
    candidate_mean: float
    delta: float
    normalized_improvement: float
    win_rate: float
    lower_bound: float
    upper_bound: float
    regressed: bool


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    proposal_id: str
    cases: int
    baseline_success_rate: float
    candidate_success_rate: float
    metrics: tuple[PairedMetricResult, ...]
    weighted_improvement: float
    critical_regressions: tuple[str, ...]
    passed: bool
    fingerprint: str


class PairedEvaluator:
    """Evaluate candidate vs baseline on the same holdout cases."""

    def __init__(self, metric_specs: Sequence[MetricSpec]) -> None:
        specs = tuple(metric_specs)
        if not specs or any(not isinstance(spec, MetricSpec) for spec in specs):
            raise ValueError("metric_specs must contain MetricSpec")
        if len({spec.name for spec in specs}) != len(specs):
            raise ValueError("duplicate metric spec")
        self.specs = specs

    def compare(
        self,
        proposal_id: str,
        baseline: Sequence[EvaluationObservation],
        candidate: Sequence[EvaluationObservation],
        *,
        minimum_cases: int = 8,
        minimum_weighted_improvement: float = 0.0,
    ) -> EvaluationReport:
        proposal_id = require_id("proposal_id", proposal_id)
        minimum_cases = positive_int("minimum_cases", minimum_cases, maximum=1_000_000)
        baseline_by_id = {item.case_id: item for item in baseline}
        candidate_by_id = {item.case_id: item for item in candidate}
        common = sorted(set(baseline_by_id) & set(candidate_by_id))
        if len(common) < minimum_cases:
            raise EvolutionError(f"insufficient paired evaluation cases: {len(common)} < {minimum_cases}")
        paired_results: list[PairedMetricResult] = []
        critical_regressions: list[str] = []
        weighted_numerator = 0.0
        weight_total = 0.0
        for spec in self.specs:
            base_values: list[float] = []
            candidate_values: list[float] = []
            deltas: list[float] = []
            wins = 0
            for case_id in common:
                left = baseline_by_id[case_id].metrics.get(spec.name)
                right = candidate_by_id[case_id].metrics.get(spec.name)
                if left is None or right is None:
                    continue
                base_values.append(left)
                candidate_values.append(right)
                raw_delta = right - left
                aligned_delta = raw_delta if spec.direction is MetricDirection.HIGHER_IS_BETTER else -raw_delta
                deltas.append(aligned_delta)
                if aligned_delta > 0:
                    wins += 1
                elif aligned_delta == 0:
                    wins += 0.5
            if not deltas:
                if spec.critical:
                    critical_regressions.append(f"missing critical metric: {spec.name}")
                continue
            baseline_mean = statistics.fmean(base_values)
            candidate_mean = statistics.fmean(candidate_values)
            raw_delta = candidate_mean - baseline_mean
            aligned = raw_delta if spec.direction is MetricDirection.HIGHER_IS_BETTER else -raw_delta
            scale = max(1e-9, abs(baseline_mean), statistics.pstdev(base_values) if len(base_values) > 1 else 0.0)
            normalized = aligned / scale
            win_rate = wins / len(deltas)
            lower, upper = self._mean_delta_interval(deltas)
            floor_failed = spec.floor is not None and (
                candidate_mean < spec.floor if spec.direction is MetricDirection.HIGHER_IS_BETTER else candidate_mean > spec.floor
            )
            regressed = aligned < -spec.maximum_regression or floor_failed
            if regressed and spec.critical:
                critical_regressions.append(spec.name)
            paired_results.append(PairedMetricResult(spec.name, baseline_mean, candidate_mean, raw_delta, normalized, win_rate, lower, upper, regressed))
            weighted_numerator += normalized * spec.weight
            weight_total += spec.weight
        weighted = weighted_numerator / weight_total if weight_total else -1.0
        baseline_success = sum(1 for case_id in common if baseline_by_id[case_id].success) / len(common)
        candidate_success = sum(1 for case_id in common if candidate_by_id[case_id].success) / len(common)
        passed = not critical_regressions and weighted >= minimum_weighted_improvement and candidate_success >= baseline_success - 0.01
        payload = {
            "proposal": proposal_id,
            "cases": len(common),
            "baseline_success": baseline_success,
            "candidate_success": candidate_success,
            "metrics": [(value.metric, value.delta, value.normalized_improvement, value.win_rate, value.regressed) for value in paired_results],
            "weighted": weighted,
            "critical": critical_regressions,
            "passed": passed,
        }
        return EvaluationReport(proposal_id, len(common), baseline_success, candidate_success, tuple(paired_results), weighted, tuple(critical_regressions), passed, stable_fingerprint(payload))

    @staticmethod
    def _mean_delta_interval(values: Sequence[float]) -> tuple[float, float]:
        mean = statistics.fmean(values)
        if len(values) < 2:
            return mean, mean
        standard_error = statistics.stdev(values) / math.sqrt(len(values))
        radius = 1.96 * standard_error
        return mean - radius, mean + radius


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    minimum_proposal_confidence: float = 0.70
    minimum_support_trajectories: int = 3
    minimum_holdout_cases: int = 12
    minimum_weighted_improvement: float = 0.015
    minimum_canary_cases: int = 8
    maximum_canary_regression_rate: float = 0.10
    maximum_active_canaries: int = 4
    require_reversible: bool = True

    def __post_init__(self) -> None:
        for name in ("minimum_proposal_confidence", "maximum_canary_regression_rate"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in ("minimum_support_trajectories", "minimum_holdout_cases", "minimum_canary_cases", "maximum_active_canaries"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1_000_000))
        improvement = finite_number("minimum_weighted_improvement", self.minimum_weighted_improvement)
        object.__setattr__(self, "minimum_weighted_improvement", improvement)


@dataclass(frozen=True, slots=True)
class CanaryObservation:
    case_id: str
    baseline_success: bool
    candidate_success: bool
    baseline_score: float
    candidate_score: float
    safety_regression: bool = False
    grounding_regression: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", require_id("case_id", self.case_id))
        object.__setattr__(self, "baseline_score", probability("baseline_score", self.baseline_score))
        object.__setattr__(self, "candidate_score", probability("candidate_score", self.candidate_score))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class CanaryReport:
    proposal_id: str
    cases: int
    candidate_win_rate: float
    regression_rate: float
    safety_regressions: int
    grounding_regressions: int
    passed: bool
    fingerprint: str


class CanaryGate:
    def __init__(self, policy: PromotionPolicy | None = None) -> None:
        self.policy = policy or PromotionPolicy()

    def evaluate(self, proposal_id: str, observations: Sequence[CanaryObservation]) -> CanaryReport:
        proposal_id = require_id("proposal_id", proposal_id)
        observations = tuple(observations)
        if len(observations) < self.policy.minimum_canary_cases:
            raise EvolutionError("insufficient canary observations")
        wins = 0.0
        regressions = 0
        safety = 0
        grounding = 0
        for item in observations:
            if item.candidate_score > item.baseline_score:
                wins += 1.0
            elif item.candidate_score == item.baseline_score:
                wins += 0.5
            if item.candidate_success is False and item.baseline_success is True:
                regressions += 1
            if item.safety_regression:
                safety += 1
            if item.grounding_regression:
                grounding += 1
        win_rate = wins / len(observations)
        regression_rate = regressions / len(observations)
        passed = regression_rate <= self.policy.maximum_canary_regression_rate and safety == 0 and grounding == 0 and win_rate >= 0.5
        payload = {"proposal": proposal_id, "cases": len(observations), "wins": win_rate, "regressions": regression_rate, "safety": safety, "grounding": grounding, "passed": passed}
        return CanaryReport(proposal_id, len(observations), win_rate, regression_rate, safety, grounding, passed, stable_fingerprint(payload))


@dataclass(frozen=True, slots=True)
class EvolutionRevision:
    revision_id: str
    parent_revision_id: str | None
    proposal_id: str | None
    state: Mapping[str, Any]
    status: ProposalStatus
    created_at: float
    fingerprint: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class EvolutionRegistry:
    """Content-addressed revision graph with rollback and optimistic activation."""

    def __init__(self, initial_state: Mapping[str, Any], *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        state = json_safe(dict(initial_state))
        root_id = stable_id("revision", {"parent": None, "state": state})
        root = EvolutionRevision(root_id, None, None, state, ProposalStatus.PROMOTED, self._clock(), stable_fingerprint(state), {"root": True})
        self._revisions: dict[str, EvolutionRevision] = {root_id: root}
        self._active_revision_id = root_id
        self._proposals: dict[str, EvolutionProposal] = {}
        self._evaluation_reports: dict[str, EvaluationReport] = {}
        self._canary_reports: dict[str, CanaryReport] = {}
        self._lock = threading.RLock()

    @property
    def active(self) -> EvolutionRevision:
        with self._lock:
            return self._revisions[self._active_revision_id]

    def proposal(self, proposal_id: str) -> EvolutionProposal | None:
        with self._lock:
            return self._proposals.get(require_id("proposal_id", proposal_id))

    def register(self, proposal: EvolutionProposal) -> EvolutionProposal:
        if not isinstance(proposal, EvolutionProposal):
            raise TypeError("proposal must be EvolutionProposal")
        with self._lock:
            if proposal.parent_revision_id != self._active_revision_id:
                raise EvolutionError("proposal parent is not current active revision")
            existing = self._proposals.get(proposal.proposal_id)
            if existing is not None:
                if existing.fingerprint != proposal.fingerprint:
                    raise EvolutionError("proposal id collision")
                return existing
            self._proposals[proposal.proposal_id] = proposal
            return proposal

    def attach_evaluation(self, report: EvaluationReport) -> None:
        with self._lock:
            if report.proposal_id not in self._proposals:
                raise EvolutionError("unknown proposal")
            self._evaluation_reports[report.proposal_id] = report
            proposal = self._proposals[report.proposal_id]
            self._proposals[report.proposal_id] = replace(proposal, status=ProposalStatus.VALIDATED if report.passed else ProposalStatus.REJECTED)

    def start_canary(self, proposal_id: str) -> EvolutionProposal:
        proposal_id = require_id("proposal_id", proposal_id)
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            report = self._evaluation_reports.get(proposal_id)
            if proposal is None or report is None or not report.passed:
                raise EvolutionError("proposal has not passed holdout evaluation")
            proposal = replace(proposal, status=ProposalStatus.CANARY)
            self._proposals[proposal_id] = proposal
            return proposal

    def attach_canary(self, report: CanaryReport) -> None:
        with self._lock:
            proposal = self._proposals.get(report.proposal_id)
            if proposal is None or proposal.status is not ProposalStatus.CANARY:
                raise EvolutionError("proposal is not in canary state")
            self._canary_reports[report.proposal_id] = report
            if not report.passed:
                self._proposals[report.proposal_id] = replace(proposal, status=ProposalStatus.REJECTED)

    def promote(self, proposal_id: str, *, expected_parent_revision: str | None = None) -> EvolutionRevision:
        proposal_id = require_id("proposal_id", proposal_id)
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            evaluation = self._evaluation_reports.get(proposal_id)
            canary = self._canary_reports.get(proposal_id)
            if proposal is None or evaluation is None or canary is None:
                raise EvolutionError("proposal lacks evaluation/canary evidence")
            if not evaluation.passed or not canary.passed:
                raise EvolutionError("proposal failed evaluation or canary")
            if expected_parent_revision is not None and expected_parent_revision != self._active_revision_id:
                raise EvolutionError("active revision changed during promotion")
            if proposal.parent_revision_id != self._active_revision_id:
                raise EvolutionError("proposal is stale relative to active revision")
            current = self.active
            next_state = self._apply_patches(current.state, proposal.patches)
            revision_id = stable_id("revision", {"parent": current.revision_id, "proposal": proposal_id, "state": next_state})
            revision = EvolutionRevision(revision_id, current.revision_id, proposal_id, next_state, ProposalStatus.PROMOTED, self._clock(), stable_fingerprint(next_state), {"evaluation": evaluation.fingerprint, "canary": canary.fingerprint})
            self._revisions[revision_id] = revision
            self._active_revision_id = revision_id
            self._proposals[proposal_id] = replace(proposal, status=ProposalStatus.PROMOTED)
            for other_id, other in list(self._proposals.items()):
                if other_id != proposal_id and other.parent_revision_id == current.revision_id and other.status in {ProposalStatus.DRAFT, ProposalStatus.VALIDATED, ProposalStatus.CANARY}:
                    self._proposals[other_id] = replace(other, status=ProposalStatus.SUPERSEDED)
            return revision

    def rollback(self, revision_id: str) -> EvolutionRevision:
        revision_id = require_id("revision_id", revision_id)
        with self._lock:
            target = self._revisions.get(revision_id)
            if target is None:
                raise EvolutionError("unknown revision")
            active = self.active
            rollback_id = stable_id("revision", {"rollback_from": active.revision_id, "target": target.revision_id, "state": target.state})
            rollback = EvolutionRevision(rollback_id, active.revision_id, active.proposal_id, target.state, ProposalStatus.ROLLED_BACK, self._clock(), target.fingerprint, {"rollback_target": target.revision_id})
            self._revisions[rollback_id] = rollback
            self._active_revision_id = rollback_id
            return rollback

    @staticmethod
    def _apply_patches(state: Mapping[str, Any], patches: Sequence[EvolutionPatch]) -> Mapping[str, Any]:
        result = dict(json_safe(dict(state)))
        for patch in patches:
            current = result.get(patch.path)
            current_fingerprint = stable_fingerprint(current)
            if current_fingerprint != patch.before_fingerprint:
                raise EvolutionError(f"patch precondition mismatch at {patch.path}")
            result[patch.path] = patch.after_payload
        return json_safe(result)

    def history(self) -> tuple[EvolutionRevision, ...]:
        with self._lock:
            values = list(self._revisions.values())
        values.sort(key=lambda value: (value.created_at, value.revision_id))
        return tuple(values)


class EvaluationHarness(Protocol):
    def run_baseline(self, case_id: str, revision: EvolutionRevision) -> EvaluationObservation:
        ...

    def run_candidate(self, case_id: str, revision: EvolutionRevision, proposal: EvolutionProposal) -> EvaluationObservation:
        ...


class EvolutionEngine:
    def __init__(
        self,
        registry: EvolutionRegistry,
        evaluator: PairedEvaluator,
        *,
        policy: PromotionPolicy | None = None,
        canary_gate: CanaryGate | None = None,
    ) -> None:
        self.registry = registry
        self.evaluator = evaluator
        self.policy = policy or PromotionPolicy()
        self.canary = canary_gate or CanaryGate(self.policy)

    def propose_from_lessons(
        self,
        lessons: Sequence[LessonCandidate],
        *,
        target: EvolutionTarget,
        path: str,
        current_payload: Any,
        transform: Callable[[Any, Sequence[LessonCandidate]], Any],
        description: str,
    ) -> EvolutionProposal:
        usable = [lesson for lesson in lessons if lesson.promote and lesson.confidence >= self.policy.minimum_proposal_confidence]
        trajectory_ids = sorted({trajectory_id for lesson in usable for trajectory_id in lesson.support_trajectory_ids})
        if len(trajectory_ids) < self.policy.minimum_support_trajectories:
            raise EvolutionError("insufficient independent trajectory support")
        after = json_safe(transform(current_payload, usable))
        patch = EvolutionPatch(target, path, stable_fingerprint(current_payload), after, description, True, {"lessons": [lesson.lesson_id for lesson in usable]})
        hypothesis = f"Applying {target.value} patch at {path} should improve future verified task performance based on {len(usable)} repeated lessons."
        payload = {"parent": self.registry.active.revision_id, "patch": patch.fingerprint, "lessons": [lesson.lesson_id for lesson in usable], "trajectories": trajectory_ids}
        proposal = EvolutionProposal(
            proposal_id=stable_id("evolution", payload),
            parent_revision_id=self.registry.active.revision_id,
            patches=(patch,),
            hypothesis=hypothesis,
            support_trajectory_ids=tuple(trajectory_ids),
            support_lesson_ids=tuple(lesson.lesson_id for lesson in usable),
            confidence=statistics.fmean(lesson.confidence for lesson in usable),
        )
        return self.registry.register(proposal)

    def evaluate_holdout(self, proposal_id: str, case_ids: Sequence[str], harness: EvaluationHarness) -> EvaluationReport:
        proposal = self.registry.proposal(proposal_id)
        if proposal is None:
            raise EvolutionError("unknown proposal")
        baseline: list[EvaluationObservation] = []
        candidate: list[EvaluationObservation] = []
        revision = self.registry.active
        for case_id in case_ids:
            case_id = require_id("case_id", case_id)
            baseline.append(harness.run_baseline(case_id, revision))
            candidate.append(harness.run_candidate(case_id, revision, proposal))
        report = self.evaluator.compare(
            proposal_id,
            baseline,
            candidate,
            minimum_cases=self.policy.minimum_holdout_cases,
            minimum_weighted_improvement=self.policy.minimum_weighted_improvement,
        )
        self.registry.attach_evaluation(report)
        return report

    def begin_canary(self, proposal_id: str) -> EvolutionProposal:
        active_canaries = sum(1 for proposal in self.registry._proposals.values() if proposal.status is ProposalStatus.CANARY)
        if active_canaries >= self.policy.maximum_active_canaries:
            raise EvolutionError("maximum active canaries reached")
        return self.registry.start_canary(proposal_id)

    def finish_canary(self, proposal_id: str, observations: Sequence[CanaryObservation]) -> CanaryReport:
        report = self.canary.evaluate(proposal_id, observations)
        self.registry.attach_canary(report)
        return report

    def promote(self, proposal_id: str) -> EvolutionRevision:
        proposal = self.registry.proposal(proposal_id)
        if proposal is None:
            raise EvolutionError("unknown proposal")
        if self.policy.require_reversible and any(not patch.reversible for patch in proposal.patches):
            raise EvolutionError("promotion policy requires reversible patches")
        return self.registry.promote(proposal_id, expected_parent_revision=proposal.parent_revision_id)


@dataclass(frozen=True, slots=True)
class OffPolicyEstimate:
    estimate: float
    effective_sample_size: float
    clipped_fraction: float
    trustworthy: bool


class OffPolicyEvaluator:
    """Clipped importance-weighted estimator for historical policy comparison.

    This is a screening signal only; it is not sufficient for promotion.
    """

    def __init__(self, *, maximum_importance_weight: float = 10.0, minimum_effective_sample_size: float = 20.0) -> None:
        cap = finite_number("maximum_importance_weight", maximum_importance_weight)
        ess = finite_number("minimum_effective_sample_size", minimum_effective_sample_size)
        if cap <= 1 or ess <= 0:
            raise ValueError("invalid off-policy evaluator configuration")
        self.cap = cap
        self.minimum_ess = ess

    def estimate(self, rewards: Sequence[float], behavior_probabilities: Sequence[float], candidate_probabilities: Sequence[float]) -> OffPolicyEstimate:
        if not (len(rewards) == len(behavior_probabilities) == len(candidate_probabilities)) or not rewards:
            raise EvolutionError("off-policy arrays must be non-empty and equal length")
        weighted_reward = 0.0
        weight_total = 0.0
        squared_weight_total = 0.0
        clipped = 0
        for reward, behavior, candidate in zip(rewards, behavior_probabilities, candidate_probabilities):
            reward = finite_number("reward", reward)
            behavior = probability("behavior_probability", behavior)
            candidate = probability("candidate_probability", candidate)
            if behavior <= 1e-9:
                continue
            weight = candidate / behavior
            if weight > self.cap:
                weight = self.cap
                clipped += 1
            weighted_reward += weight * reward
            weight_total += weight
            squared_weight_total += weight * weight
        if weight_total <= 0:
            return OffPolicyEstimate(0.0, 0.0, 1.0, False)
        estimate = weighted_reward / weight_total
        ess = weight_total * weight_total / max(1e-9, squared_weight_total)
        clipped_fraction = clipped / len(rewards)
        trustworthy = ess >= self.minimum_ess and clipped_fraction <= 0.25
        return OffPolicyEstimate(estimate, ess, clipped_fraction, trustworthy)
