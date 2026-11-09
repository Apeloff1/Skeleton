"""Dynamic test-time compute and deliberation for Jeeves.

The core idea is simple: not every step deserves the same amount of reasoning.
This module turns that into a deterministic host-side contract.  It decides how
much compute may be spent from measurable signals, then provides bounded search
primitives for stateless specialist proposals, beam/best-first exploration,
adversarial challenge, and counterfactual discrimination.

The engine never exposes or stores private chain-of-thought.  Candidate nodes
contain concise *decision summaries*, predicted outcomes, evidence references,
and host-computed scores.  Model-specific reasoning stays inside providers.
"""

from __future__ import annotations

import heapq
import math
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from .types import (
    AgentContractError,
    EvidenceRef,
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


class DeliberationError(RuntimeError):
    pass


class DeliberationMode(str, Enum):
    DIRECT = "direct"
    PLAN = "plan"
    DELIBERATE = "deliberate"
    BEAM = "beam"
    BEST_FIRST = "best_first"
    ADVERSARIAL = "adversarial"
    COUNTERFACTUAL = "counterfactual"
    COMMITTEE = "committee"


class SpecialistRole(str, Enum):
    SOLVER = "solver"
    PLANNER = "planner"
    RETRIEVER = "retriever"
    CRITIC = "critic"
    VERIFIER = "verifier"
    COUNTEREXAMPLE = "counterexample"
    RISK = "risk"
    SIMULATOR = "simulator"


@dataclass(frozen=True, slots=True)
class ComputeSignals:
    complexity: float = 0.5
    uncertainty: float = 0.5
    novelty: float = 0.5
    contradiction: float = 0.0
    expected_information_gain: float = 0.0
    failure_pressure: float = 0.0
    risk: RiskTier = RiskTier.READ_ONLY
    context_saturation: float = 0.0
    empirical_skill_reliability: float = 0.5
    deadline_pressure: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "complexity",
            "uncertainty",
            "novelty",
            "contradiction",
            "expected_information_gain",
            "failure_pressure",
            "context_saturation",
            "empirical_skill_reliability",
            "deadline_pressure",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))


@dataclass(frozen=True, slots=True)
class ComputeBudget:
    max_model_calls: int = 8
    max_candidates: int = 32
    max_depth: int = 4
    max_tokens: int = 24_000
    max_wall_seconds: float = 45.0
    beam_width: int = 4
    adversarial_rounds: int = 2

    def __post_init__(self) -> None:
        for name in ("max_model_calls", "max_candidates", "max_depth", "max_tokens", "beam_width", "adversarial_rounds"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1_000_000))
        wall = finite_number("max_wall_seconds", self.max_wall_seconds)
        if wall <= 0 or wall > 3600:
            raise AgentContractError("max_wall_seconds must be in (0, 3600]")
        object.__setattr__(self, "max_wall_seconds", wall)


@dataclass(frozen=True, slots=True)
class ComputeAllocation:
    mode: DeliberationMode
    budget: ComputeBudget
    expected_value: float
    rationale: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ComputePolicy:
    direct_threshold: float = 0.24
    plan_threshold: float = 0.40
    search_threshold: float = 0.62
    adversarial_threshold: float = 0.72
    contradiction_weight: float = 0.18
    uncertainty_weight: float = 0.18
    complexity_weight: float = 0.18
    novelty_weight: float = 0.10
    failure_weight: float = 0.12
    risk_weight: float = 0.14
    information_gain_weight: float = 0.10

    def __post_init__(self) -> None:
        for name in ("direct_threshold", "plan_threshold", "search_threshold", "adversarial_threshold"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if not self.direct_threshold <= self.plan_threshold <= self.search_threshold <= self.adversarial_threshold:
            raise AgentContractError("compute thresholds must be non-decreasing")
        weights = [
            finite_number(name, getattr(self, name))
            for name in (
                "contradiction_weight",
                "uncertainty_weight",
                "complexity_weight",
                "novelty_weight",
                "failure_weight",
                "risk_weight",
                "information_gain_weight",
            )
        ]
        if any(value < 0 for value in weights) or sum(weights) <= 0:
            raise AgentContractError("compute policy weights must be non-negative and non-zero")

    @property
    def normalized_weights(self) -> Mapping[str, float]:
        raw = {
            "contradiction": self.contradiction_weight,
            "uncertainty": self.uncertainty_weight,
            "complexity": self.complexity_weight,
            "novelty": self.novelty_weight,
            "failure": self.failure_weight,
            "risk": self.risk_weight,
            "information_gain": self.information_gain_weight,
        }
        total = sum(raw.values())
        return {key: value / total for key, value in raw.items()}


class DynamicComputeAllocator:
    _RISK = {
        RiskTier.READ_ONLY: 0.05,
        RiskTier.REVERSIBLE: 0.20,
        RiskTier.MUTATING: 0.55,
        RiskTier.EXTERNAL: 0.75,
        RiskTier.HIGH_IMPACT: 1.00,
    }

    def __init__(self, policy: ComputePolicy | None = None) -> None:
        self.policy = policy or ComputePolicy()

    def allocate(self, signals: ComputeSignals, *, global_budget_fraction_remaining: float = 1.0) -> ComputeAllocation:
        if not isinstance(signals, ComputeSignals):
            raise TypeError("signals must be ComputeSignals")
        remaining = probability("global_budget_fraction_remaining", global_budget_fraction_remaining)
        weights = self.policy.normalized_weights
        score = (
            signals.contradiction * weights["contradiction"]
            + signals.uncertainty * weights["uncertainty"]
            + signals.complexity * weights["complexity"]
            + signals.novelty * weights["novelty"]
            + signals.failure_pressure * weights["failure"]
            + self._RISK[signals.risk] * weights["risk"]
            + signals.expected_information_gain * weights["information_gain"]
        )
        # Reliable learned skills reduce the need for expensive deliberation;
        # saturated context and deadline pressure reduce feasible compute.
        score *= 1.0 - 0.20 * signals.empirical_skill_reliability
        feasible = remaining * (1.0 - 0.45 * signals.deadline_pressure) * (1.0 - 0.20 * signals.context_saturation)
        effective = max(0.0, min(1.0, score * (0.55 + 0.45 * feasible)))
        reasons = self._reasons(signals, effective, remaining)
        if effective < self.policy.direct_threshold:
            mode = DeliberationMode.DIRECT
            budget = ComputeBudget(max_model_calls=1, max_candidates=1, max_depth=1, max_tokens=2_048, max_wall_seconds=8, beam_width=1, adversarial_rounds=1)
        elif effective < self.policy.plan_threshold:
            mode = DeliberationMode.PLAN
            budget = ComputeBudget(max_model_calls=2, max_candidates=4, max_depth=2, max_tokens=5_000, max_wall_seconds=15, beam_width=2, adversarial_rounds=1)
        elif effective < self.policy.search_threshold:
            mode = DeliberationMode.DELIBERATE
            budget = ComputeBudget(max_model_calls=4, max_candidates=12, max_depth=3, max_tokens=10_000, max_wall_seconds=25, beam_width=3, adversarial_rounds=1)
        elif effective < self.policy.adversarial_threshold:
            mode = DeliberationMode.BEAM
            budget = ComputeBudget(max_model_calls=8, max_candidates=32, max_depth=4, max_tokens=24_000, max_wall_seconds=45, beam_width=4, adversarial_rounds=2)
        else:
            mode = DeliberationMode.ADVERSARIAL if signals.contradiction + self._RISK[signals.risk] >= 0.9 else DeliberationMode.BEST_FIRST
            budget = ComputeBudget(max_model_calls=12, max_candidates=64, max_depth=6, max_tokens=40_000, max_wall_seconds=75, beam_width=6, adversarial_rounds=3)
        budget = self._scale_budget(budget, feasible)
        return ComputeAllocation(
            mode=mode,
            budget=budget,
            expected_value=effective,
            rationale=reasons,
            fingerprint=stable_fingerprint({"mode": mode.value, "score": effective, "budget": self._budget_dict(budget), "signals": self._signal_dict(signals)}),
        )

    @staticmethod
    def _scale_budget(budget: ComputeBudget, feasible: float) -> ComputeBudget:
        factor = max(0.25, min(1.0, feasible))
        return ComputeBudget(
            max_model_calls=max(1, round(budget.max_model_calls * factor)),
            max_candidates=max(1, round(budget.max_candidates * factor)),
            max_depth=max(1, round(budget.max_depth * (0.6 + 0.4 * factor))),
            max_tokens=max(512, round(budget.max_tokens * factor)),
            max_wall_seconds=max(3.0, budget.max_wall_seconds * factor),
            beam_width=max(1, round(budget.beam_width * factor)),
            adversarial_rounds=max(1, round(budget.adversarial_rounds * factor)),
        )

    @staticmethod
    def _reasons(signals: ComputeSignals, score: float, remaining: float) -> tuple[str, ...]:
        ranked = sorted(
            {
                "uncertainty": signals.uncertainty,
                "complexity": signals.complexity,
                "contradiction": signals.contradiction,
                "novelty": signals.novelty,
                "failure pressure": signals.failure_pressure,
                "information gain": signals.expected_information_gain,
            }.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        reasons = [f"{name}={value:.3f}" for name, value in ranked[:3] if value >= 0.25]
        reasons.append(f"effective compute value={score:.3f}")
        reasons.append(f"global budget remaining={remaining:.3f}")
        return tuple(reasons)

    @staticmethod
    def _budget_dict(budget: ComputeBudget) -> dict[str, Any]:
        return {
            "model_calls": budget.max_model_calls,
            "candidates": budget.max_candidates,
            "depth": budget.max_depth,
            "tokens": budget.max_tokens,
            "wall": budget.max_wall_seconds,
            "beam": budget.beam_width,
            "adversarial_rounds": budget.adversarial_rounds,
        }

    @staticmethod
    def _signal_dict(signals: ComputeSignals) -> dict[str, Any]:
        return {
            "complexity": signals.complexity,
            "uncertainty": signals.uncertainty,
            "novelty": signals.novelty,
            "contradiction": signals.contradiction,
            "information_gain": signals.expected_information_gain,
            "failure": signals.failure_pressure,
            "risk": signals.risk.value,
            "context_saturation": signals.context_saturation,
            "skill_reliability": signals.empirical_skill_reliability,
            "deadline": signals.deadline_pressure,
        }


@dataclass(frozen=True, slots=True)
class CandidateProposal:
    candidate_id: str
    parent_id: str | None
    depth: int
    role: SpecialistRole
    summary: str
    proposed_action: str
    predicted_outcome: str
    confidence: float
    evidence: tuple[EvidenceRef, ...] = ()
    assumptions: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    expected_cost: float = 0.0
    expected_latency_ms: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", require_id("candidate_id", self.candidate_id))
        if self.parent_id is not None:
            object.__setattr__(self, "parent_id", require_id("parent_id", self.parent_id))
        if isinstance(self.depth, bool) or not isinstance(self.depth, int) or self.depth < 0:
            raise AgentContractError("candidate depth must be non-negative integer")
        if not isinstance(self.role, SpecialistRole):
            object.__setattr__(self, "role", SpecialistRole(str(self.role)))
        object.__setattr__(self, "summary", bounded_text("summary", self.summary, maximum=8192))
        object.__setattr__(self, "proposed_action", bounded_text("proposed_action", self.proposed_action, maximum=8192))
        object.__setattr__(self, "predicted_outcome", bounded_text("predicted_outcome", self.predicted_outcome, maximum=8192))
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        refs = tuple(self.evidence)
        if any(not isinstance(ref, EvidenceRef) for ref in refs):
            raise AgentContractError("candidate evidence must contain EvidenceRef")
        object.__setattr__(self, "evidence", refs)
        object.__setattr__(self, "assumptions", tuple(bounded_text("assumption", item, maximum=2048) for item in self.assumptions))
        object.__setattr__(self, "risks", tuple(bounded_text("risk", item, maximum=2048) for item in self.risks))
        cost = finite_number("expected_cost", self.expected_cost)
        latency = finite_number("expected_latency_ms", self.expected_latency_ms)
        if cost < 0 or latency < 0:
            raise AgentContractError("candidate cost/latency must be non-negative")
        object.__setattr__(self, "expected_cost", cost)
        object.__setattr__(self, "expected_latency_ms", latency)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "parent": self.parent_id,
                "depth": self.depth,
                "role": self.role.value,
                "summary": self.summary,
                "action": self.proposed_action,
                "outcome": self.predicted_outcome,
                "confidence": self.confidence,
                "evidence": [(ref.evidence_id, ref.fingerprint) for ref in self.evidence],
                "assumptions": self.assumptions,
                "risks": self.risks,
            }
        )


@dataclass(frozen=True, slots=True)
class CandidateScore:
    candidate_id: str
    utility: float
    evidence_quality: float
    confidence_quality: float
    risk_penalty: float
    cost_penalty: float
    novelty_bonus: float
    verifier_score: float
    total: float
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", require_id("candidate_id", self.candidate_id))
        for name in ("utility", "evidence_quality", "confidence_quality", "risk_penalty", "cost_penalty", "novelty_bonus", "verifier_score", "total"):
            value = finite_number(name, getattr(self, name))
            object.__setattr__(self, name, max(-1.0, min(1.0, value)))


class ProposalGenerator(Protocol):
    def __call__(self, task: str, parent: CandidateProposal | None, role: SpecialistRole, width: int) -> Sequence[CandidateProposal]: ...


class ProposalVerifier(Protocol):
    def __call__(self, candidate: CandidateProposal) -> float: ...


@dataclass(slots=True)
class ComputeLedger:
    started_at: float
    model_calls: int = 0
    candidates: int = 0
    estimated_tokens: int = 0
    verifier_calls: int = 0
    pruned: int = 0
    expanded: int = 0
    duplicate_candidates: int = 0

    def within(self, budget: ComputeBudget, *, now: float) -> bool:
        return (
            self.model_calls < budget.max_model_calls
            and self.candidates < budget.max_candidates
            and self.estimated_tokens < budget.max_tokens
            and now - self.started_at < budget.max_wall_seconds
        )

    def snapshot(self, *, now: float) -> dict[str, Any]:
        return {
            "model_calls": self.model_calls,
            "candidates": self.candidates,
            "estimated_tokens": self.estimated_tokens,
            "verifier_calls": self.verifier_calls,
            "pruned": self.pruned,
            "expanded": self.expanded,
            "duplicate_candidates": self.duplicate_candidates,
            "elapsed_seconds": max(0.0, now - self.started_at),
        }


@dataclass(frozen=True, slots=True)
class SearchResult:
    mode: DeliberationMode
    best: CandidateProposal | None
    ranking: tuple[tuple[CandidateProposal, CandidateScore], ...]
    explored: tuple[CandidateProposal, ...]
    ledger: Mapping[str, Any]
    stopped_reason: str
    trace_fingerprint: str


@dataclass(frozen=True, slots=True)
class ScoringWeights:
    utility: float = 0.25
    evidence: float = 0.20
    confidence: float = 0.12
    verifier: float = 0.25
    novelty: float = 0.08
    risk: float = 0.06
    cost: float = 0.04

    def normalized(self) -> Mapping[str, float]:
        values = {name: finite_number(name, getattr(self, name)) for name in ("utility", "evidence", "confidence", "verifier", "novelty", "risk", "cost")}
        if any(value < 0 for value in values.values()) or sum(values.values()) <= 0:
            raise AgentContractError("scoring weights invalid")
        total = sum(values.values())
        return {key: value / total for key, value in values.items()}


class CandidateScorer:
    def __init__(self, *, weights: ScoringWeights | None = None, verifier: ProposalVerifier | None = None) -> None:
        self.weights = (weights or ScoringWeights()).normalized()
        self.verifier = verifier
        self._seen_actions: Counter[str] = Counter()

    def score(self, candidate: CandidateProposal, *, sibling_fingerprints: set[str] | None = None) -> CandidateScore:
        evidence_quality = sum(ref.confidence for ref in candidate.evidence) / len(candidate.evidence) if candidate.evidence else 0.25
        confidence_quality = 1.0 - abs(candidate.confidence - evidence_quality) if candidate.evidence else candidate.confidence * 0.75
        utility = candidate.confidence * (0.7 + 0.3 * evidence_quality)
        risk_penalty = min(1.0, len(candidate.risks) * 0.12)
        normalized_cost = 1.0 - math.exp(-(candidate.expected_cost + candidate.expected_latency_ms / 20_000.0))
        novelty = 1.0 if not sibling_fingerprints or candidate.fingerprint not in sibling_fingerprints else 0.0
        action_count = self._seen_actions[candidate.proposed_action]
        novelty *= 1.0 / (1.0 + action_count * 0.5)
        verifier_score = probability("verifier_score", self.verifier(candidate)) if self.verifier is not None else 0.5
        w = self.weights
        total = (
            utility * w["utility"]
            + evidence_quality * w["evidence"]
            + confidence_quality * w["confidence"]
            + verifier_score * w["verifier"]
            + novelty * w["novelty"]
            - risk_penalty * w["risk"]
            - normalized_cost * w["cost"]
        )
        self._seen_actions[candidate.proposed_action] += 1
        reasons = (
            f"utility={utility:.3f}",
            f"evidence={evidence_quality:.3f}",
            f"verifier={verifier_score:.3f}",
            f"novelty={novelty:.3f}",
            f"risk_penalty={risk_penalty:.3f}",
        )
        return CandidateScore(candidate.candidate_id, utility, evidence_quality, confidence_quality, risk_penalty, normalized_cost, novelty, verifier_score, max(-1.0, min(1.0, total)), reasons)


class DeliberationEngine:
    def __init__(
        self,
        generator: ProposalGenerator,
        *,
        scorer: CandidateScorer | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not callable(generator):
            raise TypeError("generator must be callable")
        self.generator = generator
        self.scorer = scorer or CandidateScorer()
        self._clock = clock
        self._lock = threading.RLock()

    def search(self, task: str, allocation: ComputeAllocation) -> SearchResult:
        task = bounded_text("task", task, maximum=64_000)
        if not isinstance(allocation, ComputeAllocation):
            raise TypeError("allocation must be ComputeAllocation")
        mode = allocation.mode
        if mode in {DeliberationMode.DIRECT, DeliberationMode.PLAN, DeliberationMode.DELIBERATE, DeliberationMode.COMMITTEE}:
            return self._committee(task, allocation)
        if mode is DeliberationMode.BEAM:
            return self._beam(task, allocation)
        if mode is DeliberationMode.BEST_FIRST:
            return self._best_first(task, allocation)
        if mode is DeliberationMode.ADVERSARIAL:
            return self._adversarial(task, allocation)
        if mode is DeliberationMode.COUNTERFACTUAL:
            return self._counterfactual(task, allocation)
        raise DeliberationError(f"unsupported deliberation mode: {mode}")

    def _roles_for(self, mode: DeliberationMode) -> tuple[SpecialistRole, ...]:
        if mode is DeliberationMode.DIRECT:
            return (SpecialistRole.SOLVER,)
        if mode is DeliberationMode.PLAN:
            return (SpecialistRole.PLANNER, SpecialistRole.CRITIC)
        if mode is DeliberationMode.DELIBERATE:
            return (SpecialistRole.SOLVER, SpecialistRole.PLANNER, SpecialistRole.CRITIC, SpecialistRole.VERIFIER)
        return (SpecialistRole.SOLVER, SpecialistRole.PLANNER, SpecialistRole.RETRIEVER, SpecialistRole.CRITIC, SpecialistRole.VERIFIER, SpecialistRole.RISK)

    def _committee(self, task: str, allocation: ComputeAllocation) -> SearchResult:
        ledger = ComputeLedger(self._clock())
        explored: list[CandidateProposal] = []
        ranking: list[tuple[CandidateProposal, CandidateScore]] = []
        fingerprints: set[str] = set()
        roles = self._roles_for(allocation.mode)
        width = max(1, allocation.budget.beam_width // max(1, len(roles)))
        for role in roles:
            if not ledger.within(allocation.budget, now=self._clock()):
                break
            proposals = tuple(self.generator(task, None, role, width))
            ledger.model_calls += 1
            for candidate in proposals:
                self._validate_generated(candidate, parent=None, budget=allocation.budget)
                ledger.candidates += 1
                ledger.estimated_tokens += self._estimate_candidate_tokens(candidate)
                if candidate.fingerprint in fingerprints:
                    ledger.duplicate_candidates += 1
                    continue
                score = self.scorer.score(candidate, sibling_fingerprints=fingerprints)
                fingerprints.add(candidate.fingerprint)
                explored.append(candidate)
                ranking.append((candidate, score))
                if ledger.candidates >= allocation.budget.max_candidates:
                    break
        ranking.sort(key=lambda item: (item[1].total, item[0].confidence, item[0].candidate_id), reverse=True)
        best = ranking[0][0] if ranking else None
        return self._result(allocation.mode, best, ranking, explored, ledger, "committee complete")

    def _beam(self, task: str, allocation: ComputeAllocation) -> SearchResult:
        budget = allocation.budget
        ledger = ComputeLedger(self._clock())
        roots = self._generate(task, None, SpecialistRole.PLANNER, budget.beam_width, ledger, budget)
        explored = list(roots)
        ranking = self._score_many(roots)
        beam = [candidate for candidate, _ in ranking[: budget.beam_width]]
        depth = 1
        while beam and depth < budget.max_depth and ledger.within(budget, now=self._clock()):
            next_candidates: list[CandidateProposal] = []
            for parent in beam:
                if not ledger.within(budget, now=self._clock()):
                    break
                width = max(1, budget.beam_width)
                generated = self._generate(task, parent, SpecialistRole.SOLVER, width, ledger, budget)
                next_candidates.extend(generated)
                explored.extend(generated)
                ledger.expanded += 1
            next_ranking = self._score_many(next_candidates)
            ranking.extend(next_ranking)
            next_ranking.sort(key=lambda item: (item[1].total, item[0].confidence), reverse=True)
            beam = [candidate for candidate, _ in next_ranking[: budget.beam_width]]
            depth += 1
        ranking = self._dedupe_ranking(ranking)
        best = ranking[0][0] if ranking else None
        reason = "beam budget exhausted" if not ledger.within(budget, now=self._clock()) else "beam depth complete"
        return self._result(DeliberationMode.BEAM, best, ranking, explored, ledger, reason)

    def _best_first(self, task: str, allocation: ComputeAllocation) -> SearchResult:
        budget = allocation.budget
        ledger = ComputeLedger(self._clock())
        roots = self._generate(task, None, SpecialistRole.PLANNER, budget.beam_width, ledger, budget)
        explored: list[CandidateProposal] = list(roots)
        ranking: list[tuple[CandidateProposal, CandidateScore]] = []
        frontier: list[tuple[float, int, CandidateProposal]] = []
        counter = 0
        for candidate, score in self._score_many(roots):
            ranking.append((candidate, score))
            counter += 1
            heapq.heappush(frontier, (-score.total, counter, candidate))
        while frontier and ledger.within(budget, now=self._clock()):
            _, _, parent = heapq.heappop(frontier)
            if parent.depth >= budget.max_depth:
                ledger.pruned += 1
                continue
            generated = self._generate(task, parent, SpecialistRole.SOLVER, budget.beam_width, ledger, budget)
            ledger.expanded += 1
            explored.extend(generated)
            for candidate, score in self._score_many(generated):
                ranking.append((candidate, score))
                counter += 1
                # optimistic bound rewards shallower strong candidates.
                priority = score.total + max(0.0, 0.08 * (budget.max_depth - candidate.depth))
                heapq.heappush(frontier, (-priority, counter, candidate))
            if len(frontier) > budget.max_candidates:
                frontier = heapq.nsmallest(budget.max_candidates, frontier)
                heapq.heapify(frontier)
        ranking = self._dedupe_ranking(ranking)
        best = ranking[0][0] if ranking else None
        return self._result(DeliberationMode.BEST_FIRST, best, ranking, explored, ledger, "best-first search complete")

    def _adversarial(self, task: str, allocation: ComputeAllocation) -> SearchResult:
        budget = allocation.budget
        ledger = ComputeLedger(self._clock())
        initial = self._generate(task, None, SpecialistRole.SOLVER, budget.beam_width, ledger, budget)
        explored: list[CandidateProposal] = list(initial)
        ranking = self._score_many(initial)
        ranking.sort(key=lambda item: item[1].total, reverse=True)
        incumbent = ranking[0][0] if ranking else None
        for round_index in range(budget.adversarial_rounds):
            if incumbent is None or not ledger.within(budget, now=self._clock()):
                break
            critics = self._generate(task, incumbent, SpecialistRole.COUNTEREXAMPLE, max(1, budget.beam_width // 2), ledger, budget)
            explored.extend(critics)
            critic_ranking = self._score_many(critics)
            ranking.extend(critic_ranking)
            strongest_critic = max(critic_ranking, key=lambda item: item[1].total)[0] if critic_ranking else None
            if strongest_critic is None or not ledger.within(budget, now=self._clock()):
                continue
            repairs = self._generate(task, strongest_critic, SpecialistRole.SOLVER, budget.beam_width, ledger, budget)
            explored.extend(repairs)
            repair_ranking = self._score_many(repairs)
            ranking.extend(repair_ranking)
            combined = [(incumbent, self.scorer.score(incumbent))] + repair_ranking
            combined.sort(key=lambda item: (item[1].total, item[0].confidence), reverse=True)
            incumbent = combined[0][0]
        ranking = self._dedupe_ranking(ranking)
        best = ranking[0][0] if ranking else incumbent
        return self._result(DeliberationMode.ADVERSARIAL, best, ranking, explored, ledger, "adversarial rounds complete")

    def _counterfactual(self, task: str, allocation: ComputeAllocation) -> SearchResult:
        budget = allocation.budget
        ledger = ComputeLedger(self._clock())
        simulations = self._generate(task, None, SpecialistRole.SIMULATOR, budget.beam_width, ledger, budget)
        explored = list(simulations)
        ranking = self._score_many(simulations)
        if simulations and ledger.within(budget, now=self._clock()):
            for parent in simulations[: budget.beam_width]:
                challengers = self._generate(task, parent, SpecialistRole.COUNTEREXAMPLE, 1, ledger, budget)
                explored.extend(challengers)
                ranking.extend(self._score_many(challengers))
        ranking = self._dedupe_ranking(ranking)
        best = ranking[0][0] if ranking else None
        return self._result(DeliberationMode.COUNTERFACTUAL, best, ranking, explored, ledger, "counterfactual simulation complete")

    def _generate(
        self,
        task: str,
        parent: CandidateProposal | None,
        role: SpecialistRole,
        width: int,
        ledger: ComputeLedger,
        budget: ComputeBudget,
    ) -> tuple[CandidateProposal, ...]:
        if not ledger.within(budget, now=self._clock()):
            return ()
        width = max(1, min(width, budget.max_candidates - ledger.candidates))
        if width <= 0:
            return ()
        proposals = tuple(self.generator(task, parent, role, width))
        ledger.model_calls += 1
        accepted: list[CandidateProposal] = []
        for candidate in proposals[:width]:
            self._validate_generated(candidate, parent=parent, budget=budget)
            ledger.candidates += 1
            ledger.estimated_tokens += self._estimate_candidate_tokens(candidate)
            accepted.append(candidate)
            if not ledger.within(budget, now=self._clock()):
                break
        return tuple(accepted)

    @staticmethod
    def _validate_generated(candidate: CandidateProposal, *, parent: CandidateProposal | None, budget: ComputeBudget) -> None:
        if not isinstance(candidate, CandidateProposal):
            raise DeliberationError("generator returned non-CandidateProposal")
        expected_depth = 0 if parent is None else parent.depth + 1
        if candidate.depth != expected_depth:
            raise DeliberationError("candidate depth does not follow parent")
        if parent is not None and candidate.parent_id != parent.candidate_id:
            raise DeliberationError("candidate parent_id mismatch")
        if candidate.depth >= budget.max_depth + 1:
            raise DeliberationError("candidate exceeds deliberation depth budget")

    def _score_many(self, candidates: Sequence[CandidateProposal]) -> list[tuple[CandidateProposal, CandidateScore]]:
        sibling_fps: set[str] = set()
        scored: list[tuple[CandidateProposal, CandidateScore]] = []
        for candidate in candidates:
            score = self.scorer.score(candidate, sibling_fingerprints=sibling_fps)
            sibling_fps.add(candidate.fingerprint)
            scored.append((candidate, score))
        scored.sort(key=lambda item: (item[1].total, item[0].confidence, item[0].candidate_id), reverse=True)
        return scored

    @staticmethod
    def _dedupe_ranking(ranking: Sequence[tuple[CandidateProposal, CandidateScore]]) -> list[tuple[CandidateProposal, CandidateScore]]:
        best_by_fp: dict[str, tuple[CandidateProposal, CandidateScore]] = {}
        for candidate, score in ranking:
            prior = best_by_fp.get(candidate.fingerprint)
            if prior is None or score.total > prior[1].total:
                best_by_fp[candidate.fingerprint] = (candidate, score)
        values = list(best_by_fp.values())
        values.sort(key=lambda item: (item[1].total, item[0].confidence, item[0].candidate_id), reverse=True)
        return values

    @staticmethod
    def _estimate_candidate_tokens(candidate: CandidateProposal) -> int:
        chars = len(candidate.summary) + len(candidate.proposed_action) + len(candidate.predicted_outcome)
        chars += sum(len(item) for item in candidate.assumptions) + sum(len(item) for item in candidate.risks)
        return max(1, chars // 4)

    def _result(
        self,
        mode: DeliberationMode,
        best: CandidateProposal | None,
        ranking: Sequence[tuple[CandidateProposal, CandidateScore]],
        explored: Sequence[CandidateProposal],
        ledger: ComputeLedger,
        stopped_reason: str,
    ) -> SearchResult:
        now = self._clock()
        ledger_snapshot = ledger.snapshot(now=now)
        trace = stable_fingerprint(
            {
                "mode": mode.value,
                "best": best.candidate_id if best else None,
                "ranking": [(candidate.candidate_id, score.total) for candidate, score in ranking],
                "explored": [(candidate.candidate_id, candidate.fingerprint) for candidate in explored],
                "ledger": ledger_snapshot,
                "reason": stopped_reason,
            }
        )
        return SearchResult(mode, best, tuple(ranking), tuple(explored), ledger_snapshot, stopped_reason, trace)


@dataclass(frozen=True, slots=True)
class DebatePosition:
    role: SpecialistRole
    candidate: CandidateProposal
    score: CandidateScore


@dataclass(frozen=True, slots=True)
class CouncilResult:
    positions: tuple[DebatePosition, ...]
    selected: CandidateProposal | None
    dissent: tuple[CandidateProposal, ...]
    agreement: float
    fingerprint: str


class DeliberationCouncil:
    """Stateful orchestrator over otherwise stateless specialist proposals."""

    def __init__(self, engine: DeliberationEngine) -> None:
        self.engine = engine

    def convene(self, task: str, allocation: ComputeAllocation) -> CouncilResult:
        roles = self.engine._roles_for(DeliberationMode.COMMITTEE)
        ledger = ComputeLedger(self.engine._clock())
        positions: list[DebatePosition] = []
        for role in roles:
            if not ledger.within(allocation.budget, now=self.engine._clock()):
                break
            candidates = self.engine._generate(task, None, role, 1, ledger, allocation.budget)
            for candidate, score in self.engine._score_many(candidates):
                positions.append(DebatePosition(role, candidate, score))
        positions.sort(key=lambda position: (position.score.total, position.candidate.confidence), reverse=True)
        selected = positions[0].candidate if positions else None
        action_counts = Counter(position.candidate.proposed_action for position in positions)
        agreement = max(action_counts.values(), default=0) / len(positions) if positions else 0.0
        dissent = tuple(position.candidate for position in positions if selected is not None and position.candidate.proposed_action != selected.proposed_action)
        return CouncilResult(
            positions=tuple(positions),
            selected=selected,
            dissent=dissent,
            agreement=agreement,
            fingerprint=stable_fingerprint(
                {
                    "positions": [(position.role.value, position.candidate.fingerprint, position.score.total) for position in positions],
                    "selected": selected.candidate_id if selected else None,
                    "agreement": agreement,
                }
            ),
        )


def proposal(
    *,
    role: SpecialistRole,
    summary: str,
    proposed_action: str,
    predicted_outcome: str,
    confidence: float,
    parent: CandidateProposal | None = None,
    evidence: Sequence[EvidenceRef] = (),
    assumptions: Sequence[str] = (),
    risks: Sequence[str] = (),
    expected_cost: float = 0.0,
    expected_latency_ms: float = 0.0,
    metadata: Mapping[str, Any] | None = None,
) -> CandidateProposal:
    depth = 0 if parent is None else parent.depth + 1
    content = {
        "role": role.value,
        "parent": parent.candidate_id if parent else None,
        "depth": depth,
        "summary": summary,
        "action": proposed_action,
        "outcome": predicted_outcome,
        "evidence": [(ref.evidence_id, ref.fingerprint) for ref in evidence],
    }
    return CandidateProposal(
        candidate_id=stable_id("candidate", content),
        parent_id=parent.candidate_id if parent else None,
        depth=depth,
        role=role,
        summary=summary,
        proposed_action=proposed_action,
        predicted_outcome=predicted_outcome,
        confidence=confidence,
        evidence=tuple(evidence),
        assumptions=tuple(assumptions),
        risks=tuple(risks),
        expected_cost=expected_cost,
        expected_latency_ms=expected_latency_ms,
        metadata=metadata or {},
    )
