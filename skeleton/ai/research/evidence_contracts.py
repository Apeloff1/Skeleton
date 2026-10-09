"""Typed, fail-closed evidence contracts for bounded scientific research.

These contracts preserve source identity, experimental preregistration, negative
results, and the exact evidence graph used to support a conclusion.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Iterable


class ResearchError(ValueError):
    """A research evidence or experiment contract is invalid."""


class Outcome(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEGATIVE = "negative"
    AMBIGUOUS = "ambiguous"


def _canonical(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ResearchError("value is not canonically encodable") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchError(f"{label} must be non-empty text")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ResearchQuestion:
    question_id: str
    question: str
    scope: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_text(self.question_id, "question_id")
        _required_text(self.question, "question")
        _required_text(self.scope, "scope")
        if not self.limitations or any(not isinstance(x, str) or not x.strip() for x in self.limitations):
            raise ResearchError("question requires explicit limitations")


@dataclass(frozen=True, slots=True)
class EvidenceNode:
    evidence_id: str
    source_id: str
    source_digest: str
    method: str
    claim_ids: tuple[str, ...]
    outcome: Outcome

    def __post_init__(self) -> None:
        for label in ("evidence_id", "source_id", "source_digest", "method"):
            _required_text(getattr(self, label), label)
        if not isinstance(self.claim_ids, tuple) or not self.claim_ids:
            raise ResearchError("claim_ids must be a non-empty tuple")
        if any(not isinstance(x, str) or not x.strip() for x in self.claim_ids):
            raise ResearchError("claim_ids must contain non-empty identifiers")
        if not isinstance(self.outcome, Outcome):
            raise ResearchError("Outcome enum required")

    @property
    def digest(self) -> str:
        return _digest({
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "source_digest": self.source_digest,
            "method": self.method,
            "claim_ids": self.claim_ids,
            "outcome": self.outcome.value,
        })


class EvidenceGraph:
    """Append-only evidence graph keyed by immutable evidence identifiers."""

    def __init__(self) -> None:
        self._nodes: dict[str, EvidenceNode] = {}

    def add(self, node: EvidenceNode) -> None:
        if not isinstance(node, EvidenceNode):
            raise ResearchError("EvidenceNode required")
        prior = self._nodes.get(node.evidence_id)
        if prior is not None and prior != node:
            raise ResearchError("evidence identity is immutable")
        self._nodes[node.evidence_id] = node

    def for_claim(self, claim_id: str) -> tuple[EvidenceNode, ...]:
        _required_text(claim_id, "claim_id")
        return tuple(node for node in self._nodes.values() if claim_id in node.claim_ids)


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    experiment_id: str
    hypothesis: str
    metrics: tuple[str, ...]
    decision_rule: str
    max_trials: int

    def __post_init__(self) -> None:
        for label in ("experiment_id", "hypothesis", "decision_rule"):
            _required_text(getattr(self, label), label)
        if not isinstance(self.metrics, tuple) or not self.metrics or any(not isinstance(x, str) or not x.strip() for x in self.metrics):
            raise ResearchError("preregistered metrics are required")
        if len(set(self.metrics)) != len(self.metrics):
            raise ResearchError("duplicate preregistered metrics")
        if isinstance(self.max_trials, bool) or not isinstance(self.max_trials, int) or not 1 <= self.max_trials <= 10000:
            raise ResearchError("max_trials must be a positive integer no greater than 10000")

    @property
    def digest(self) -> str:
        return _digest({
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "metrics": self.metrics,
            "decision_rule": self.decision_rule,
            "max_trials": self.max_trials,
        })


@dataclass(frozen=True, slots=True)
class ReproductionRecord:
    reproduction_id: str
    evidence_digest: str
    experiment_digest: str
    metrics: tuple[tuple[str, float], ...]
    outcome: Outcome
    trials: int

    def __post_init__(self) -> None:
        for label in ("reproduction_id", "evidence_digest", "experiment_digest"):
            _required_text(getattr(self, label), label)
        if not isinstance(self.metrics, tuple) or not self.metrics:
            raise ResearchError("reproduction metrics are required")
        names: set[str] = set()
        for pair in self.metrics:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ResearchError("metrics must be name/value pairs")
            name, value = pair
            _required_text(name, "metric name")
            if name in names:
                raise ResearchError("duplicate reproduction metric")
            names.add(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError("metric values must be finite numbers")
        if not isinstance(self.outcome, Outcome):
            raise ResearchError("Outcome enum required")
        if isinstance(self.trials, bool) or not isinstance(self.trials, int) or self.trials < 1:
            raise ResearchError("trials must be a positive integer")

    @property
    def digest(self) -> str:
        return _digest({
            "reproduction_id": self.reproduction_id,
            "evidence_digest": self.evidence_digest,
            "experiment_digest": self.experiment_digest,
            "metrics": self.metrics,
            "outcome": self.outcome.value,
            "trials": self.trials,
        })


def validate_reproduction(evidence: EvidenceNode, plan: ExperimentPlan, record: ReproductionRecord) -> None:
    if not isinstance(evidence, EvidenceNode) or not isinstance(plan, ExperimentPlan) or not isinstance(record, ReproductionRecord):
        raise ResearchError("evidence, experiment plan, and reproduction record are required")
    if record.evidence_digest != evidence.digest or record.experiment_digest != plan.digest:
        raise ResearchError("reproduction is stale or bound to different evidence/experiment")
    if record.trials > plan.max_trials:
        raise ResearchError("reproduction exceeds preregistered trial budget")
    if {name for name, _ in record.metrics} != set(plan.metrics):
        raise ResearchError("reproduction metrics do not match preregistration")


@dataclass(frozen=True, slots=True)
class ResearchConclusion:
    conclusion_id: str
    question_id: str
    claim_id: str
    evidence_digests: tuple[str, ...]
    outcomes: tuple[Outcome, ...]
    conclusion: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for label in ("conclusion_id", "question_id", "claim_id", "conclusion"):
            _required_text(getattr(self, label), label)
        if not self.evidence_digests or len(self.evidence_digests) != len(self.outcomes):
            raise ResearchError("conclusion must bind each outcome to evidence")
        if any(not isinstance(x, Outcome) for x in self.outcomes):
            raise ResearchError("conclusion outcomes must be Outcome enums")
        if not self.limitations or any(not isinstance(x, str) or not x.strip() for x in self.limitations):
            raise ResearchError("conclusion limitations must be explicit")
        if any(x in {Outcome.NEGATIVE, Outcome.CONTRADICTS} for x in self.outcomes):
            if not any("conflicting_or_negative_evidence" in x for x in self.limitations):
                raise ResearchError("negative evidence must be disclosed in limitations")


def synthesize(
    question: ResearchQuestion,
    claim_id: str,
    graph: EvidenceGraph,
    conclusion: str,
    limitations: Iterable[str],
) -> ResearchConclusion:
    if not isinstance(question, ResearchQuestion) or not isinstance(graph, EvidenceGraph):
        raise ResearchError("research question and evidence graph required")
    nodes = graph.for_claim(claim_id)
    if not nodes:
        raise ResearchError("unsupported claim: no bound evidence")
    outcomes = tuple(node.outcome for node in nodes)
    limits = tuple(dict.fromkeys((*question.limitations, *tuple(limitations))))
    if any(x in {Outcome.NEGATIVE, Outcome.CONTRADICTS} for x in outcomes):
        limits = tuple(dict.fromkeys((*limits, "conflicting_or_negative_evidence")))
    return ResearchConclusion(
        conclusion_id="CONCLUSION." + _digest((question.question_id, claim_id, tuple(n.digest for n in nodes)))[:16],
        question_id=question.question_id,
        claim_id=claim_id,
        evidence_digests=tuple(node.digest for node in nodes),
        outcomes=outcomes,
        conclusion=conclusion,
        limitations=limits,
    )


__all__ = [
    "EvidenceGraph", "EvidenceNode", "ExperimentPlan", "Outcome",
    "ReproductionRecord", "ResearchConclusion", "ResearchError",
    "ResearchQuestion", "synthesize", "validate_reproduction",
]
