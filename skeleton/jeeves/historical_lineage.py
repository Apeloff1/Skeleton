"""Model-generation lineage and drift analysis for Jeeves.

Historical rankings compare model revisions as independent candidates.  This
module adds an explicit lineage graph so successive revisions can be compared on
the exact same holdout evidence without pretending that version strings encode
ancestry.

Lineage is metadata only.  It never rewrites benchmark evidence and never makes
a runtime provider executable.  Drift reports are derived from an existing
``HistoricalPromotionGate`` and therefore inherit its immutable suite/window
contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from skeleton.jeeves.historical_evaluation import HistoricalPromotionGate, HoldoutEvaluation
from skeleton.jeeves.historical_models import BenchmarkDomain, ModelIdentity, canonical_fingerprint


MAX_LINEAGE_NODES: Final = 1_024


class HistoricalLineageError(ValueError):
    """Fail-closed lineage or drift contract violation."""


class DriftDirection(str, Enum):
    IMPROVED = "improved"
    STABLE = "stable"
    REGRESSED = "regressed"


def _bounded_text(name: str, value: object, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalLineageError(f"{name} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise HistoricalLineageError(f"{name} exceeds {maximum} characters")
    return cleaned


def _unit(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalLineageError(f"{name} must be numeric")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise HistoricalLineageError(f"{name} must be between 0 and 1")
    return number


@dataclass(frozen=True, slots=True)
class LineageNode:
    model: ModelIdentity
    family: str
    generation: int
    parent: ModelIdentity | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model, ModelIdentity):
            raise HistoricalLineageError("model must be ModelIdentity")
        object.__setattr__(self, "family", _bounded_text("family", self.family))
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation <= 0:
            raise HistoricalLineageError("generation must be a positive integer")
        if self.parent is not None and not isinstance(self.parent, ModelIdentity):
            raise HistoricalLineageError("parent must be ModelIdentity or None")
        if self.parent == self.model:
            raise HistoricalLineageError("a model cannot parent itself")


@dataclass(frozen=True, slots=True)
class DriftPolicy:
    material_delta: float = 0.01
    severe_regression: float = 0.05
    max_regressed_domains: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "material_delta", _unit("material_delta", self.material_delta))
        object.__setattr__(self, "severe_regression", _unit("severe_regression", self.severe_regression))
        if self.severe_regression < self.material_delta:
            raise HistoricalLineageError("severe_regression must be >= material_delta")
        if isinstance(self.max_regressed_domains, bool) or not isinstance(self.max_regressed_domains, int):
            raise HistoricalLineageError("max_regressed_domains must be an integer")
        if self.max_regressed_domains < 0:
            raise HistoricalLineageError("max_regressed_domains must be non-negative")


@dataclass(frozen=True, slots=True)
class DomainDrift:
    domain: BenchmarkDomain
    parent_score: float
    child_score: float
    delta: float
    direction: DriftDirection


@dataclass(frozen=True, slots=True)
class GenerationDriftReport:
    parent: ModelIdentity
    child: ModelIdentity
    family: str
    parent_generation: int
    child_generation: int
    parent_score: float
    child_score: float
    aggregate_delta: float
    domains: tuple[DomainDrift, ...]
    regressed_domains: tuple[BenchmarkDomain, ...]
    improved_domains: tuple[BenchmarkDomain, ...]
    severe_regression: bool
    structural_break: bool
    parent_evidence_fingerprint: str
    child_evidence_fingerprint: str
    report_fingerprint: str


class ModelLineage:
    """Append-only explicit ancestry graph for model revisions."""

    def __init__(self, *, max_nodes: int = MAX_LINEAGE_NODES) -> None:
        if isinstance(max_nodes, bool) or not isinstance(max_nodes, int) or max_nodes <= 0:
            raise HistoricalLineageError("max_nodes must be a positive integer")
        self.max_nodes = max_nodes
        self._nodes: dict[ModelIdentity, LineageNode] = {}

    def register(self, node: LineageNode) -> None:
        if not isinstance(node, LineageNode):
            raise HistoricalLineageError("node must be LineageNode")
        if node.model in self._nodes:
            raise HistoricalLineageError(f"model already registered: {node.model.key}")
        if len(self._nodes) >= self.max_nodes:
            raise HistoricalLineageError("lineage node limit reached")
        siblings = [item for item in self._nodes.values() if item.family == node.family]
        if not siblings:
            if node.parent is not None:
                raise HistoricalLineageError("first family node must be a root")
            if node.generation != 1:
                raise HistoricalLineageError("root generation must be 1")
        else:
            if node.parent is None:
                raise HistoricalLineageError("non-root family nodes require a parent")
            parent = self._nodes.get(node.parent)
            if parent is None:
                raise HistoricalLineageError("parent must already be registered")
            if parent.family != node.family:
                raise HistoricalLineageError("parent and child must share family")
            if parent.model.provider != node.model.provider:
                raise HistoricalLineageError("parent and child must share provider")
            if node.generation != parent.generation + 1:
                raise HistoricalLineageError("child generation must be parent generation + 1")
        if any(item.family == node.family and item.generation == node.generation for item in siblings):
            raise HistoricalLineageError("family generation is already occupied")
        self._nodes[node.model] = node

    def node(self, model: ModelIdentity) -> LineageNode:
        try:
            return self._nodes[model]
        except KeyError as exc:
            raise HistoricalLineageError(f"model is not registered: {model.key}") from exc

    def family(self, family: str) -> tuple[LineageNode, ...]:
        family = _bounded_text("family", family)
        return tuple(
            sorted(
                (node for node in self._nodes.values() if node.family == family),
                key=lambda node: (node.generation, node.model.key),
            )
        )

    def ancestors(self, model: ModelIdentity) -> tuple[LineageNode, ...]:
        current = self.node(model)
        result: list[LineageNode] = []
        while current.parent is not None:
            current = self.node(current.parent)
            result.append(current)
        return tuple(result)

    def latest(self, family: str) -> LineageNode:
        nodes = self.family(family)
        if not nodes:
            raise HistoricalLineageError(f"unknown family: {family}")
        return nodes[-1]

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            [
                {
                    "model": node.model.key,
                    "family": node.family,
                    "generation": node.generation,
                    "parent": node.parent.key if node.parent is not None else None,
                }
                for node in sorted(self._nodes.values(), key=lambda item: (item.family, item.generation, item.model.key))
            ]
        )


class GenerationDriftAnalyzer:
    """Compare parent/child generations on one immutable holdout contract."""

    def __init__(
        self,
        *,
        lineage: ModelLineage,
        gate: HistoricalPromotionGate,
        policy: DriftPolicy | None = None,
    ) -> None:
        if not isinstance(lineage, ModelLineage):
            raise HistoricalLineageError("lineage must be ModelLineage")
        if not isinstance(gate, HistoricalPromotionGate):
            raise HistoricalLineageError("gate must be HistoricalPromotionGate")
        self.lineage = lineage
        self.gate = gate
        self.policy = policy or DriftPolicy()
        if not isinstance(self.policy, DriftPolicy):
            raise HistoricalLineageError("policy must be DriftPolicy")

    def compare(self, child: ModelIdentity) -> GenerationDriftReport:
        child_node = self.lineage.node(child)
        if child_node.parent is None:
            raise HistoricalLineageError("root generations have no parent drift comparison")
        parent_node = self.lineage.node(child_node.parent)
        parent_eval = self.gate.evaluate(parent_node.model)
        child_eval = self.gate.evaluate(child_node.model)
        self._require_comparable(parent_eval)
        self._require_comparable(child_eval)

        domain_reports: list[DomainDrift] = []
        regressed: list[BenchmarkDomain] = []
        improved: list[BenchmarkDomain] = []
        severe = False
        for domain in sorted(self.gate.suite.required_domains, key=lambda item: item.value):
            parent_domain = parent_eval.domain(domain)
            child_domain = child_eval.domain(domain)
            if parent_domain is None or child_domain is None:
                raise HistoricalLineageError(f"missing required comparable domain: {domain.value}")
            delta = child_domain.score - parent_domain.score
            if delta > self.policy.material_delta:
                direction = DriftDirection.IMPROVED
                improved.append(domain)
            elif delta < -self.policy.material_delta:
                direction = DriftDirection.REGRESSED
                regressed.append(domain)
            else:
                direction = DriftDirection.STABLE
            if delta < -self.policy.severe_regression:
                severe = True
            domain_reports.append(
                DomainDrift(
                    domain=domain,
                    parent_score=parent_domain.score,
                    child_score=child_domain.score,
                    delta=delta,
                    direction=direction,
                )
            )

        aggregate_delta = child_eval.score - parent_eval.score
        structural_break = severe or len(regressed) > self.policy.max_regressed_domains
        payload = {
            "lineage_fingerprint": self.lineage.fingerprint,
            "parent": parent_node.model.key,
            "child": child_node.model.key,
            "parent_evidence": parent_eval.evidence_fingerprint,
            "child_evidence": child_eval.evidence_fingerprint,
            "suite": self.gate.suite.fingerprint,
            "window": [self.gate.window.start_at, self.gate.window.end_at],
            "aggregate_delta": aggregate_delta,
            "domains": [
                {"domain": item.domain.value, "delta": item.delta, "direction": item.direction.value}
                for item in domain_reports
            ],
            "structural_break": structural_break,
        }
        return GenerationDriftReport(
            parent=parent_node.model,
            child=child_node.model,
            family=child_node.family,
            parent_generation=parent_node.generation,
            child_generation=child_node.generation,
            parent_score=parent_eval.score,
            child_score=child_eval.score,
            aggregate_delta=aggregate_delta,
            domains=tuple(domain_reports),
            regressed_domains=tuple(regressed),
            improved_domains=tuple(improved),
            severe_regression=severe,
            structural_break=structural_break,
            parent_evidence_fingerprint=parent_eval.evidence_fingerprint,
            child_evidence_fingerprint=child_eval.evidence_fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )

    def compare_family(self, family: str) -> tuple[GenerationDriftReport, ...]:
        nodes = self.lineage.family(family)
        return tuple(self.compare(node.model) for node in nodes if node.parent is not None)

    def _require_comparable(self, evaluation: HoldoutEvaluation) -> None:
        if evaluation.missing_required_domains:
            raise HistoricalLineageError(
                f"model lacks required holdout domains: {evaluation.model.key}"
            )
        if evaluation.coverage + 1e-12 < 1.0:
            raise HistoricalLineageError(f"model has incomplete holdout coverage: {evaluation.model.key}")


def summarize_drift(report: GenerationDriftReport) -> dict[str, object]:
    return {
        "family": report.family,
        "parent": report.parent.key,
        "child": report.child.key,
        "parent_generation": report.parent_generation,
        "child_generation": report.child_generation,
        "parent_score": report.parent_score,
        "child_score": report.child_score,
        "aggregate_delta": report.aggregate_delta,
        "regressed_domains": [domain.value for domain in report.regressed_domains],
        "improved_domains": [domain.value for domain in report.improved_domains],
        "severe_regression": report.severe_regression,
        "structural_break": report.structural_break,
        "parent_evidence_fingerprint": report.parent_evidence_fingerprint,
        "child_evidence_fingerprint": report.child_evidence_fingerprint,
        "report_fingerprint": report.report_fingerprint,
        "domains": [
            {
                "domain": item.domain.value,
                "parent_score": item.parent_score,
                "child_score": item.child_score,
                "delta": item.delta,
                "direction": item.direction.value,
            }
            for item in report.domains
        ],
    }