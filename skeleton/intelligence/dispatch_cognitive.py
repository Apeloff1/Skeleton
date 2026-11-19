"""Source-bound cognitive dispatch proposals for existing Jeeves owners.

No model output can grant capability, execution, network, or tool authority.
The caller supplies independently verified observations and explicit eligible
model identities. These functions never invoke a model or publish an answer.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
import re

from .dispatch_policy import DispatchPolicyError, bounded_int, identifier, MAX_CANDIDATES


def digest(value: str) -> str:
    if type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value):
        raise DispatchPolicyError("invalid source digest")
    return value


def labels(values: frozenset[str]) -> None:
    if type(values) is not frozenset or len(values) > 128:
        raise DispatchPolicyError("invalid capability set")
    for value in values:
        identifier(value)


def binding(*values) -> str:
    return sha256(json.dumps(values, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CognitiveDemand:
    task_id: str
    tenant_id: str
    policy_sha256: str
    context_sha256: str
    task_class: str
    required: frozenset[str]
    allowed_models: frozenset[str]
    input_tokens: int
    output_tokens: int
    reasoning_steps: int
    evidence_items: int
    uncertainty_ppm: int
    deadline_ms: int
    budget_microunits: int
    local_only: bool = True
    independent_review: bool = False

    def __post_init__(self) -> None:
        for value in (self.task_id, self.tenant_id, self.task_class):
            identifier(value)
        digest(self.policy_sha256)
        digest(self.context_sha256)
        labels(self.required)
        labels(self.allowed_models)
        if not self.allowed_models:
            raise DispatchPolicyError("explicit model approval required")
        for model in self.allowed_models:
            digest(model)
        for name in ("input_tokens", "output_tokens", "reasoning_steps"):
            bounded_int(getattr(self, name), name, 1)
        for name in ("evidence_items", "deadline_ms", "budget_microunits"):
            bounded_int(getattr(self, name), name)
        bounded_int(self.uncertainty_ppm, "uncertainty", 0, 1_000_000)
        if type(self.local_only) is not bool or type(self.independent_review) is not bool:
            raise DispatchPolicyError("invalid authority flags")

    @property
    def complexity(self) -> int:
        """Explicit workload proxy; never a claim of semantic model intelligence."""
        return min(1_000_000, self.input_tokens * 4 + self.output_tokens * 8
                   + self.reasoning_steps * 100 + self.evidence_items * 50)


@dataclass(frozen=True, slots=True)
class SpecialistObservation:
    worker_id: str
    tenant_id: str
    model_sha256: str
    family_id: str
    failure_domain: str
    policy_sha256: str
    task_class: str
    capabilities: frozenset[str]
    source_sha256: str
    context_sha256: str | None
    generation: int
    observed_ms: int
    free_tokens: int
    predicted_ms: int
    cost_microunits: int
    max_complexity: int
    verified_successes: int
    verified_trials: int
    local: bool
    healthy: bool

    def __post_init__(self) -> None:
        for value in (self.worker_id, self.tenant_id, self.family_id, self.failure_domain, self.task_class):
            identifier(value)
        for value in (self.model_sha256, self.policy_sha256, self.source_sha256):
            digest(value)
        if self.context_sha256 is not None:
            digest(self.context_sha256)
        labels(self.capabilities)
        for name in ("generation", "observed_ms", "free_tokens", "cost_microunits",
                     "verified_successes", "verified_trials"):
            bounded_int(getattr(self, name), name)
        bounded_int(self.predicted_ms, "predicted duration", 1)
        bounded_int(self.max_complexity, "complexity capacity", 1, 1_000_000)
        if self.verified_successes > self.verified_trials:
            raise DispatchPolicyError("invalid quality evidence counts")
        if type(self.local) is not bool or type(self.healthy) is not bool:
            raise DispatchPolicyError("invalid health or locality")

    @property
    def quality_score(self) -> Fraction:
        # Shrink small histories toward a conservative prior. This is an
        # ordering heuristic, not a calibrated probability or confidence interval.
        return Fraction(self.verified_successes + 1, self.verified_trials + 4)


@dataclass(frozen=True, slots=True)
class SpecialistPlan:
    task_id: str
    workers: tuple[str, ...]
    models: tuple[str, ...]
    generations: tuple[int, ...]
    source_digests: tuple[str, ...]
    roles: tuple[str, ...]
    reserved_tokens: int
    reserved_cost: int
    predicted_ms: int
    disposition: str
    plan_sha256: str


def choose_specialists(demand: CognitiveDemand, candidates: Sequence[SpecialistObservation], *,
                       now_ms: int, max_age_ms: int = 5000,
                       uncertainty_review_ppm: int = 350_000,
                       min_quality_ppm: int = 500_000) -> SpecialistPlan:
    """Find an explicitly allowed specialist or independent producer/reviewer pair.

    Each candidate must have matching tenant, policy, task class and source
    observation. A secondary model must differ in family AND failure domain.
    Budget counts every role, including review, without assumed cache savings.
    Failure abstains, never silently downgrades verification.
    """
    bounded_int(now_ms, "time")
    bounded_int(max_age_ms, "observation age", 1, 60_000)
    bounded_int(uncertainty_review_ppm, "review threshold", 0, 1_000_000)
    bounded_int(min_quality_ppm, "quality floor", 0, 1_000_000)
    if not isinstance(demand, CognitiveDemand) or len(candidates) > 1024:
        raise DispatchPolicyError("invalid specialist observation")
    if any(not isinstance(c, SpecialistObservation) for c in candidates):
        raise DispatchPolicyError("invalid specialist")
    if len({c.worker_id for c in candidates}) != len(candidates):
        raise DispatchPolicyError("duplicate specialist")
    reserve = demand.input_tokens + demand.output_tokens
    eligible = [c for c in candidates if c.healthy and c.tenant_id == demand.tenant_id
                and c.model_sha256 in demand.allowed_models and c.policy_sha256 == demand.policy_sha256
                and c.task_class == demand.task_class and demand.required <= c.capabilities
                and (c.local or not demand.local_only)
                and 0 <= now_ms - c.observed_ms <= max_age_ms
                and c.free_tokens >= reserve and c.max_complexity >= demand.complexity
                and c.cost_microunits <= demand.budget_microunits
                and now_ms + c.predicted_ms <= demand.deadline_ms
                and c.quality_score >= Fraction(min_quality_ppm, 1_000_000)]
    eligible.sort(key=lambda c: (-c.quality_score, c.context_sha256 != demand.context_sha256,
                                 c.predicted_ms, c.cost_microunits, c.worker_id))
    review = demand.independent_review or demand.uncertainty_ppm >= uncertainty_review_ppm

    def receipt(rows: tuple[SpecialistObservation, ...], disposition: str) -> SpecialistPlan:
        roles = ("producer", "reviewer") if len(rows) == 2 else ("producer",) if rows else ()
        workers = tuple(c.worker_id for c in rows)
        models = tuple(c.model_sha256 for c in rows)
        generations = tuple(c.generation for c in rows)
        sources = tuple(c.source_sha256 for c in rows)
        cost = sum(c.cost_microunits for c in rows)
        duration = sum(c.predicted_ms for c in rows)
        proof = binding("specialists-v1", demand.task_id, demand.tenant_id, demand.policy_sha256,
                        demand.context_sha256, demand.task_class, sorted(demand.required),
                        sorted(demand.allowed_models), demand.input_tokens, demand.output_tokens,
                        demand.reasoning_steps, demand.evidence_items, demand.uncertainty_ppm,
                        demand.deadline_ms, demand.budget_microunits, demand.local_only,
                        demand.independent_review, now_ms, max_age_ms, uncertainty_review_ppm,
                        min_quality_ppm, workers, models, generations, sources, roles, cost,
                        duration, disposition)
        return SpecialistPlan(demand.task_id, workers, models, generations, sources, roles,
                              reserve * len(rows), cost, duration, disposition, proof)

    if not review:
        return receipt((eligible[0],), "single") if eligible else receipt((), "hold")
    for a in eligible:
        for b in eligible:
            if (a.worker_id == b.worker_id or a.model_sha256 == b.model_sha256
                    or a.family_id == b.family_id or a.failure_domain == b.failure_domain
                    or "verify" not in b.capabilities):
                continue
            if (a.cost_microunits + b.cost_microunits <= demand.budget_microunits
                    and now_ms + a.predicted_ms + b.predicted_ms <= demand.deadline_ms):
                return receipt((a, b), "independent_review")
    return receipt((), "hold_review_unavailable")


@dataclass(frozen=True, slots=True)
class HypothesisObservation:
    hypothesis_id: str
    model_sha256: str
    family_id: str
    failure_domain: str
    task_sha256: str
    result_sha256: str
    evidence_sha256: str
    verdict: str

    def __post_init__(self) -> None:
        for value in (self.hypothesis_id, self.family_id, self.failure_domain):
            identifier(value)
        for value in (self.model_sha256, self.task_sha256, self.result_sha256, self.evidence_sha256):
            digest(value)
        if self.verdict not in {"supports", "contradicts", "abstains"}:
            raise DispatchPolicyError("unknown verdict")


@dataclass(frozen=True, slots=True)
class ConsensusProposal:
    disposition: str
    result_sha256: str | None
    supporting_evidence: tuple[str, ...]


def review_hypotheses(task_sha256: str, observations: Sequence[HypothesisObservation], *,
                      minimum_independent: int = 2) -> ConsensusProposal:
    """Aggregate pre-verified evidence; agreement is not truth or publication permission."""
    digest(task_sha256)
    bounded_int(minimum_independent, "review threshold", 2, 16)
    if len(observations) > 64 or any(not isinstance(o, HypothesisObservation) for o in observations):
        raise DispatchPolicyError("invalid hypothesis observations")
    if len({o.hypothesis_id for o in observations}) != len(observations):
        raise DispatchPolicyError("duplicate hypothesis")
    if any(o.task_sha256 != task_sha256 for o in observations):
        raise DispatchPolicyError("hypothesis task mismatch")
    if any(o.verdict == "contradicts" for o in observations):
        return ConsensusProposal("hold_conflict", None, ())
    supported = {o.result_sha256 for o in observations if o.verdict == "supports"}
    if len(supported) != 1:
        return ConsensusProposal("hold_disagreement", None, ())
    result = next(iter(supported))
    families: set[str] = set()
    domains: set[str] = set()
    models: set[str] = set()
    evidence: set[str] = set()
    for o in sorted(observations, key=lambda x: x.hypothesis_id):
        if o.verdict != "supports" or o.family_id in families or o.failure_domain in domains or (
            o.model_sha256 in models or o.evidence_sha256 in evidence
        ):
            continue
        families.add(o.family_id)
        domains.add(o.failure_domain)
        models.add(o.model_sha256)
        evidence.add(o.evidence_sha256)
    if len(evidence) < minimum_independent:
        return ConsensusProposal("hold_insufficient_independence", None, ())
    return ConsensusProposal("candidate_for_external_verification", result, tuple(sorted(evidence)))
