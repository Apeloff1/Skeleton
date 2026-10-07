"""Executable P3 acceptance envelopes for autonomous work, research and SOTA-candidate claims.

These contracts deliberately qualify bounded evidence.  They do not promote
masterplan maturity and never convert a local fixture into an unscoped "SOTA"
claim.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping, Sequence


class P3AcceptanceError(RuntimeError):
    pass


def _text(name: str, value: object, limit: int = 1024) -> str:
    text = str(value).strip()
    if not text:
        raise P3AcceptanceError(f"{name} must be non-empty")
    if len(text) > limit:
        raise P3AcceptanceError(f"{name} exceeds size limit")
    return text


def _refs(name: str, values: Sequence[str], minimum: int = 1) -> tuple[str, ...]:
    refs = tuple(dict.fromkeys(_text(name, value, 512) for value in values))
    if len(refs) < minimum:
        raise P3AcceptanceError(f"{name} requires at least {minimum} unique refs")
    return refs


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


_REQUIRED_STRESS = frozenset(
    {"interruption", "stale_work", "conflict", "deadline", "resource_exhaustion"}
)


@dataclass(frozen=True, slots=True)
class AutonomousWorkerScenario:
    objective_id: str
    budget_limit: int
    budget_spent: int
    delegated_authority: tuple[str, ...]
    checkpoint_refs: tuple[str, ...]
    override_ref: str
    recovery_ref: str
    stress_conditions: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "objective_id", _text("objective_id", self.objective_id, 256))
        for name in ("budget_limit", "budget_spent"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise P3AcceptanceError(f"{name} must be a non-negative integer")
        if self.budget_limit <= 0:
            raise P3AcceptanceError("budget_limit must be positive")
        object.__setattr__(
            self,
            "delegated_authority",
            _refs("delegated_authority", self.delegated_authority),
        )
        object.__setattr__(
            self,
            "checkpoint_refs",
            _refs("checkpoint_ref", self.checkpoint_refs, minimum=2),
        )
        object.__setattr__(self, "override_ref", _text("override_ref", self.override_ref, 512))
        object.__setattr__(self, "recovery_ref", _text("recovery_ref", self.recovery_ref, 512))
        object.__setattr__(
            self,
            "stress_conditions",
            frozenset(_text("stress_condition", item, 128) for item in self.stress_conditions),
        )


@dataclass(frozen=True, slots=True)
class AutonomousWorkerAcceptance:
    objective_id: str
    budget_headroom: int
    authority_count: int
    checkpoint_count: int
    stress_conditions: tuple[str, ...]
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class ResearchClaim:
    claim_id: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _text("claim_id", self.claim_id, 256))
        object.__setattr__(
            self,
            "evidence_refs",
            _refs("claim_evidence_ref", self.evidence_refs),
        )


@dataclass(frozen=True, slots=True)
class ResearchAcceptanceCase:
    question_id: str
    claims: tuple[ResearchClaim, ...]
    contradiction_refs: tuple[str, ...]
    reproduction_refs: tuple[str, ...]
    uncertainty_ref: str
    negative_result_refs: tuple[str, ...]
    implementer_id: str
    reviewer_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _text("question_id", self.question_id, 256))
        if not self.claims:
            raise P3AcceptanceError("research acceptance requires at least one claim")
        object.__setattr__(
            self,
            "contradiction_refs",
            _refs("contradiction_ref", self.contradiction_refs),
        )
        object.__setattr__(
            self,
            "reproduction_refs",
            _refs("reproduction_ref", self.reproduction_refs),
        )
        object.__setattr__(self, "uncertainty_ref", _text("uncertainty_ref", self.uncertainty_ref, 512))
        object.__setattr__(
            self,
            "negative_result_refs",
            _refs("negative_result_ref", self.negative_result_refs),
        )
        object.__setattr__(self, "implementer_id", _text("implementer_id", self.implementer_id, 256))
        object.__setattr__(self, "reviewer_id", _text("reviewer_id", self.reviewer_id, 256))


@dataclass(frozen=True, slots=True)
class ResearchAcceptance:
    question_id: str
    claim_count: int
    evidence_ref_count: int
    reviewer_id: str
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class SOTACandidateCase:
    benchmark_id: str
    task_scope: str
    population: str
    baseline_metrics: Mapping[str, float]
    candidate_metrics: Mapping[str, float]
    contamination_audit_refs: tuple[str, ...]
    replay_refs: tuple[str, ...]
    robustness_refs: tuple[str, ...]
    security_refs: tuple[str, ...]
    latency_ms: float
    cost_per_case: float
    implementer_id: str
    verifier_id: str

    def __post_init__(self) -> None:
        for name in ("benchmark_id", "task_scope", "population", "implementer_id", "verifier_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name), 512))
        baseline = {str(k): float(v) for k, v in self.baseline_metrics.items()}
        candidate = {str(k): float(v) for k, v in self.candidate_metrics.items()}
        if not baseline or set(baseline) != set(candidate):
            raise P3AcceptanceError("candidate metrics must exactly match non-empty baseline metrics")
        if any(not key.strip() for key in baseline):
            raise P3AcceptanceError("metric names must be non-empty")
        object.__setattr__(self, "baseline_metrics", baseline)
        object.__setattr__(self, "candidate_metrics", candidate)
        for name in (
            "contamination_audit_refs",
            "replay_refs",
            "robustness_refs",
            "security_refs",
        ):
            object.__setattr__(self, name, _refs(name[:-1], getattr(self, name)))
        if self.latency_ms < 0 or self.cost_per_case < 0:
            raise P3AcceptanceError("latency and cost characterization must be non-negative")


@dataclass(frozen=True, slots=True)
class SOTACandidateQualification:
    benchmark_id: str
    task_scope: str
    population: str
    verifier_id: str
    metric_names: tuple[str, ...]
    qualification_digest: str
    claim: str = "bounded_sota_candidate"


class P3AcceptanceHarness:
    def accept_autonomous_worker(
        self,
        scenario: AutonomousWorkerScenario,
    ) -> AutonomousWorkerAcceptance:
        if scenario.budget_spent > scenario.budget_limit:
            raise P3AcceptanceError("autonomous worker exceeded declared budget")
        missing = _REQUIRED_STRESS - scenario.stress_conditions
        if missing:
            raise P3AcceptanceError(
                "autonomous worker stress coverage incomplete: " + ",".join(sorted(missing))
            )
        if not scenario.override_ref.startswith("override:"):
            raise P3AcceptanceError("autonomous worker requires explicit human override evidence")
        if not scenario.recovery_ref.startswith("recovery:"):
            raise P3AcceptanceError("autonomous worker requires durable recovery evidence")
        payload = {
            "objective_id": scenario.objective_id,
            "budget_limit": scenario.budget_limit,
            "budget_spent": scenario.budget_spent,
            "delegated_authority": scenario.delegated_authority,
            "checkpoint_refs": scenario.checkpoint_refs,
            "override_ref": scenario.override_ref,
            "recovery_ref": scenario.recovery_ref,
            "stress_conditions": sorted(scenario.stress_conditions),
        }
        return AutonomousWorkerAcceptance(
            objective_id=scenario.objective_id,
            budget_headroom=scenario.budget_limit - scenario.budget_spent,
            authority_count=len(scenario.delegated_authority),
            checkpoint_count=len(scenario.checkpoint_refs),
            stress_conditions=tuple(sorted(scenario.stress_conditions)),
            receipt_digest=_digest(payload),
        )

    def accept_research(
        self,
        case: ResearchAcceptanceCase,
    ) -> ResearchAcceptance:
        if case.implementer_id == case.reviewer_id:
            raise P3AcceptanceError("research acceptance requires independent review")
        evidence_count = sum(len(claim.evidence_refs) for claim in case.claims)
        claim_ids = [claim.claim_id for claim in case.claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise P3AcceptanceError("research claim ids must be unique")
        payload = {
            "question_id": case.question_id,
            "claims": [
                {"claim_id": claim.claim_id, "evidence_refs": claim.evidence_refs}
                for claim in case.claims
            ],
            "contradiction_refs": case.contradiction_refs,
            "reproduction_refs": case.reproduction_refs,
            "uncertainty_ref": case.uncertainty_ref,
            "negative_result_refs": case.negative_result_refs,
            "reviewer_id": case.reviewer_id,
        }
        return ResearchAcceptance(
            question_id=case.question_id,
            claim_count=len(case.claims),
            evidence_ref_count=evidence_count,
            reviewer_id=case.reviewer_id,
            receipt_digest=_digest(payload),
        )

    def qualify_sota_candidate(
        self,
        case: SOTACandidateCase,
    ) -> SOTACandidateQualification:
        if case.implementer_id == case.verifier_id:
            raise P3AcceptanceError("SOTA-candidate qualification requires independent verification")
        if not all(ref.startswith("contamination:") for ref in case.contamination_audit_refs):
            raise P3AcceptanceError("SOTA-candidate qualification requires contamination audit refs")
        if not all(ref.startswith("replay:") for ref in case.replay_refs):
            raise P3AcceptanceError("SOTA-candidate qualification requires independent replay refs")
        regressions = [
            name
            for name, baseline in case.baseline_metrics.items()
            if case.candidate_metrics[name] < baseline
        ]
        if regressions:
            raise P3AcceptanceError(
                "candidate regresses declared baseline metrics: " + ",".join(sorted(regressions))
            )
        payload = {
            "benchmark_id": case.benchmark_id,
            "task_scope": case.task_scope,
            "population": case.population,
            "baseline_metrics": case.baseline_metrics,
            "candidate_metrics": case.candidate_metrics,
            "contamination_audit_refs": case.contamination_audit_refs,
            "replay_refs": case.replay_refs,
            "robustness_refs": case.robustness_refs,
            "security_refs": case.security_refs,
            "latency_ms": case.latency_ms,
            "cost_per_case": case.cost_per_case,
            "verifier_id": case.verifier_id,
            "claim": "bounded_sota_candidate",
        }
        return SOTACandidateQualification(
            benchmark_id=case.benchmark_id,
            task_scope=case.task_scope,
            population=case.population,
            verifier_id=case.verifier_id,
            metric_names=tuple(sorted(case.baseline_metrics)),
            qualification_digest=_digest(payload),
        )


__all__ = [
    "AutonomousWorkerAcceptance",
    "AutonomousWorkerScenario",
    "P3AcceptanceError",
    "P3AcceptanceHarness",
    "ResearchAcceptance",
    "ResearchAcceptanceCase",
    "ResearchClaim",
    "SOTACandidateCase",
    "SOTACandidateQualification",
]
