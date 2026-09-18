"""Chronological scientific synthesis and no-lookahead frontier selection.

Jeeves should not equate "new" with "better".  This module replays a knowledge
base year by year, admits only information available by that year, evaluates
methods on multiple dimensions, and preserves a Pareto frontier of methods that
remain scientifically useful.

The engine is intentionally domain-neutral: probability, control, compiler
construction, verification, causality, learning, memory, cinema/narrative and
game research can share one temporal evidence protocol without sharing one
meaningless scalar score.

It is a framework for ingesting a large corpus; the bundled seed catalog is a
small set of landmarks, not a claim to contain "all research".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .context_fabric import DeepContextRecord
from .memory_game_index import CardKind, MemoryGameIndex, SourceTier
from .types import AgentContractError, bounded_text, json_safe, probability, stable_fingerprint, stable_id


class MethodFamily(str, Enum):
    PROBABILITY = "probability"
    DECISION = "decision"
    CONTROL = "control"
    INFORMATION = "information"
    COMPILER = "compiler"
    VERIFICATION = "verification"
    PROGRAM_ANALYSIS = "program_analysis"
    CAUSALITY = "causality"
    LEARNING = "learning"
    MEMORY = "memory"
    RETRIEVAL = "retrieval"
    SEMANTICS = "semantics"
    NARRATIVE = "narrative"
    CINEMA = "cinema"
    GAMES = "games"
    MULTI_AGENT = "multi_agent"


@dataclass(frozen=True, slots=True)
class HistoricalReference:
    reference_id: str
    title: str
    publication_year: int
    locator: str
    contribution: str
    limitations: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference_id", str(self.reference_id).strip().casefold())
        if not self.reference_id:
            raise AgentContractError("reference_id is required")
        object.__setattr__(self, "title", bounded_text("title", self.title, maximum=2048))
        if isinstance(self.publication_year, bool) or not isinstance(self.publication_year, int):
            raise AgentContractError("publication_year must be an integer")
        object.__setattr__(self, "locator", bounded_text("locator", self.locator, maximum=2048))
        object.__setattr__(self, "contribution", bounded_text("contribution", self.contribution, maximum=8192))
        object.__setattr__(self, "limitations", bounded_text("limitations", self.limitations, maximum=8192, allow_empty=True))


@dataclass(frozen=True, slots=True)
class EvidenceProfile:
    formal_strength: float = 0.0
    empirical_strength: float = 0.0
    replication: float = 0.0
    external_validity: float = 0.0
    reproducibility: float = 0.0
    falsifiability: float = 0.5

    def __post_init__(self) -> None:
        for name in (
            "formal_strength",
            "empirical_strength",
            "replication",
            "external_validity",
            "reproducibility",
            "falsifiability",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))

    @property
    def conservative_strength(self) -> float:
        # Harmonic mean punishes a profile that is strong on one dimension and
        # near-zero on all others, while a small floor keeps purely formal work
        # representable even when empirical axes are not applicable.
        values = (
            max(0.05, self.formal_strength),
            max(0.05, self.empirical_strength),
            max(0.05, self.replication),
            max(0.05, self.reproducibility),
            max(0.05, self.falsifiability),
        )
        return len(values) / sum(1.0 / value for value in values)


@dataclass(frozen=True, slots=True)
class QualityVector:
    correctness: float = 0.5
    calibration: float = 0.5
    robustness: float = 0.5
    compute_efficiency: float = 0.5
    sample_efficiency: float = 0.5
    memory_efficiency: float = 0.5
    interpretability: float = 0.5
    auditability: float = 0.5
    transfer: float = 0.5
    reproducibility: float = 0.5

    def __post_init__(self) -> None:
        for name in self.names():
            object.__setattr__(self, name, probability(name, getattr(self, name)))

    @classmethod
    def names(cls) -> tuple[str, ...]:
        return (
            "correctness",
            "calibration",
            "robustness",
            "compute_efficiency",
            "sample_efficiency",
            "memory_efficiency",
            "interpretability",
            "auditability",
            "transfer",
            "reproducibility",
        )

    def as_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in self.names()}

    def shrink(self, confidence: float, *, prior: float = 0.5) -> "QualityVector":
        confidence = probability("confidence", confidence)
        values = {
            name: prior + confidence * (getattr(self, name) - prior)
            for name in self.names()
        }
        return QualityVector(**values)


@dataclass(frozen=True, slots=True)
class HistoricalMethod:
    method_id: str
    name: str
    introduced_year: int
    families: tuple[MethodFamily, ...]
    thesis: str
    evidence: EvidenceProfile
    references: tuple[HistoricalReference, ...]
    assumptions: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    parent_ids: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    orthogonal_to: tuple[str, ...] = ()
    invariant_tags: tuple[str, ...] = ()
    last_updated_year: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        key = str(self.method_id).strip().casefold()
        if not key:
            raise AgentContractError("method_id is required")
        object.__setattr__(self, "method_id", key)
        object.__setattr__(self, "name", bounded_text("method name", self.name, maximum=512))
        if isinstance(self.introduced_year, bool) or not isinstance(self.introduced_year, int):
            raise AgentContractError("introduced_year must be integer")
        families = tuple(
            value if isinstance(value, MethodFamily) else MethodFamily(str(value))
            for value in self.families
        )
        if not families:
            raise AgentContractError("method must belong to at least one family")
        object.__setattr__(self, "families", tuple(sorted(set(families), key=lambda x: x.value)))
        object.__setattr__(self, "thesis", bounded_text("method thesis", self.thesis, maximum=16384))
        if not isinstance(self.evidence, EvidenceProfile):
            raise TypeError("evidence must be EvidenceProfile")
        references = tuple(self.references)
        if not references:
            raise AgentContractError("method requires at least one reference")
        if any(not isinstance(item, HistoricalReference) for item in references):
            raise TypeError("references must be HistoricalReference values")
        if min(item.publication_year for item in references) < self.introduced_year - 1:
            # A small tolerance permits publication year / conference-date
            # mismatches without permitting a century-scale chronology error.
            raise AgentContractError("reference chronology predates introduced_year unexpectedly")
        object.__setattr__(self, "references", references)
        for name in ("assumptions", "failure_modes", "parent_ids", "supersedes", "orthogonal_to", "invariant_tags"):
            object.__setattr__(
                self,
                name,
                tuple(str(value).strip() for value in getattr(self, name) if str(value).strip()),
            )
        if self.last_updated_year is not None and self.last_updated_year < self.introduced_year:
            raise AgentContractError("last_updated_year cannot precede introduced_year")
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.method_id,
                "name": self.name,
                "introduced": self.introduced_year,
                "families": [value.value for value in self.families],
                "thesis": self.thesis,
                "evidence": self.evidence.__dict__ if hasattr(self.evidence, "__dict__") else {
                    "formal": self.evidence.formal_strength,
                    "empirical": self.evidence.empirical_strength,
                    "replication": self.evidence.replication,
                    "external": self.evidence.external_validity,
                    "reproducibility": self.evidence.reproducibility,
                    "falsifiability": self.evidence.falsifiability,
                },
                "references": [
                    (r.reference_id, r.publication_year, r.locator) for r in self.references
                ],
                "assumptions": self.assumptions,
                "failure_modes": self.failure_modes,
                "parents": self.parent_ids,
                "supersedes": self.supersedes,
                "orthogonal": self.orthogonal_to,
                "invariants": self.invariant_tags,
                "updated": self.last_updated_year,
            }
        )


@dataclass(frozen=True, slots=True)
class MethodEvaluation:
    evaluation_id: str
    method_id: str
    evaluation_year: int
    benchmark_id: str
    quality: QualityVector
    confidence: float
    hard_failures: tuple[str, ...] = ()
    environment_fingerprint: str = ""
    independent_run: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("evaluation_id", "method_id", "benchmark_id"):
            value = str(getattr(self, name)).strip().casefold()
            if not value:
                raise AgentContractError(f"{name} is required")
            object.__setattr__(self, name, value)
        if isinstance(self.evaluation_year, bool) or not isinstance(self.evaluation_year, int):
            raise AgentContractError("evaluation_year must be integer")
        if not isinstance(self.quality, QualityVector):
            raise TypeError("quality must be QualityVector")
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        object.__setattr__(self, "hard_failures", tuple(sorted({str(x) for x in self.hard_failures if str(x)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.evaluation_id,
                "method": self.method_id,
                "year": self.evaluation_year,
                "benchmark": self.benchmark_id,
                "quality": self.quality.as_dict(),
                "confidence": self.confidence,
                "hard_failures": self.hard_failures,
                "environment": self.environment_fingerprint,
                "run": self.independent_run,
            }
        )


@dataclass(frozen=True, slots=True)
class MethodScore:
    method_id: str
    quality: QualityVector
    evaluation_count: int
    benchmark_count: int
    latest_evaluation_year: int
    hard_failures: tuple[str, ...]
    evidence_strength: float
    scalar_score: float | None = None


@dataclass(frozen=True, slots=True)
class AnnualFrontier:
    year: int
    eligible_method_ids: tuple[str, ...]
    evaluated_method_ids: tuple[str, ...]
    pareto_method_ids: tuple[str, ...]
    promoted_method_ids: tuple[str, ...]
    retained_method_ids: tuple[str, ...]
    removed_method_ids: tuple[str, ...]
    hard_failed_method_ids: tuple[str, ...]
    unevaluated_method_ids: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class HistoricalSynthesisPolicy:
    dominance_epsilon: float = 1e-9
    minimum_evidence_strength: float = 0.05
    require_evaluation_for_frontier: bool = True
    hard_failure_is_disqualifying: bool = True
    latest_evaluation_per_benchmark: bool = True

    def __post_init__(self) -> None:
        eps = float(self.dominance_epsilon)
        if not math.isfinite(eps) or eps < 0:
            raise AgentContractError("dominance_epsilon must be finite and non-negative")
        object.__setattr__(self, "dominance_epsilon", eps)
        object.__setattr__(
            self,
            "minimum_evidence_strength",
            probability("minimum_evidence_strength", self.minimum_evidence_strength),
        )


class ChronologicalScientificFrontier:
    """Append-only historical corpus with strict no-future-leakage replay."""

    def __init__(self, *, policy: HistoricalSynthesisPolicy | None = None) -> None:
        self.policy = policy or HistoricalSynthesisPolicy()
        self._methods: dict[str, HistoricalMethod] = {}
        self._evaluations: dict[str, MethodEvaluation] = {}

    def register_method(self, method: HistoricalMethod) -> HistoricalMethod:
        if not isinstance(method, HistoricalMethod):
            raise TypeError("method must be HistoricalMethod")
        existing = self._methods.get(method.method_id)
        if existing is not None and existing.fingerprint != method.fingerprint:
            raise AgentContractError(f"method id collision: {method.method_id}")
        for parent in method.parent_ids:
            known = self._methods.get(parent)
            if known is not None and known.introduced_year > method.introduced_year:
                raise AgentContractError("method parent cannot originate in the future")
        self._methods[method.method_id] = method
        return method

    def record_evaluation(self, evaluation: MethodEvaluation) -> MethodEvaluation:
        if not isinstance(evaluation, MethodEvaluation):
            raise TypeError("evaluation must be MethodEvaluation")
        method = self._methods.get(evaluation.method_id)
        if method is None:
            raise AgentContractError("evaluation references unknown method")
        if evaluation.evaluation_year < method.introduced_year:
            raise AgentContractError("evaluation cannot predate method introduction")
        existing = self._evaluations.get(evaluation.evaluation_id)
        if existing is not None and existing.fingerprint != evaluation.fingerprint:
            raise AgentContractError(f"evaluation id collision: {evaluation.evaluation_id}")
        self._evaluations[evaluation.evaluation_id] = evaluation
        return evaluation

    def methods_known_by(self, year: int) -> tuple[HistoricalMethod, ...]:
        return tuple(
            sorted(
                (method for method in self._methods.values() if method.introduced_year <= year),
                key=lambda item: (item.introduced_year, item.method_id),
            )
        )

    def evaluations_known_by(self, year: int, *, method_id: str | None = None) -> tuple[MethodEvaluation, ...]:
        values = [
            item
            for item in self._evaluations.values()
            if item.evaluation_year <= year and (method_id is None or item.method_id == method_id)
        ]
        return tuple(sorted(values, key=lambda item: (item.evaluation_year, item.benchmark_id, item.evaluation_id)))

    def _evaluation_slice(self, method_id: str, year: int) -> tuple[MethodEvaluation, ...]:
        rows = list(self.evaluations_known_by(year, method_id=method_id))
        if not self.policy.latest_evaluation_per_benchmark:
            return tuple(rows)
        latest: dict[str, MethodEvaluation] = {}
        for row in rows:
            prior = latest.get(row.benchmark_id)
            if prior is None or (row.evaluation_year, row.evaluation_id) > (prior.evaluation_year, prior.evaluation_id):
                latest[row.benchmark_id] = row
        return tuple(sorted(latest.values(), key=lambda item: (item.benchmark_id, item.evaluation_id)))

    def score(self, method_id: str, year: int, *, weights: Mapping[str, float] | None = None) -> MethodScore | None:
        method = self._methods.get(str(method_id).casefold())
        if method is None or method.introduced_year > year:
            return None
        rows = self._evaluation_slice(method.method_id, year)
        if not rows:
            return None
        hard_failures = tuple(sorted({failure for row in rows for failure in row.hard_failures}))
        weighted: dict[str, float] = {}
        total_confidence = sum(max(1e-9, row.confidence) for row in rows)
        for name in QualityVector.names():
            value = 0.0
            for row in rows:
                conservative = row.quality.shrink(row.confidence)
                value += getattr(conservative, name) * max(1e-9, row.confidence)
            weighted[name] = value / total_confidence
        vector = QualityVector(**weighted)
        scalar = None
        if weights:
            scalar = self._weighted_score(vector, weights)
        return MethodScore(
            method_id=method.method_id,
            quality=vector,
            evaluation_count=len(rows),
            benchmark_count=len({row.benchmark_id for row in rows}),
            latest_evaluation_year=max(row.evaluation_year for row in rows),
            hard_failures=hard_failures,
            evidence_strength=method.evidence.conservative_strength,
            scalar_score=scalar,
        )

    @staticmethod
    def _weighted_score(vector: QualityVector, weights: Mapping[str, float]) -> float:
        unknown = set(weights) - set(QualityVector.names())
        if unknown:
            raise AgentContractError(f"unknown quality weights: {sorted(unknown)}")
        values = {key: float(value) for key, value in weights.items()}
        if any(not math.isfinite(value) or value < 0 for value in values.values()):
            raise AgentContractError("quality weights must be finite and non-negative")
        total = sum(values.values())
        if total <= 0:
            raise AgentContractError("at least one quality weight must be positive")
        return sum(getattr(vector, key) * value for key, value in values.items()) / total

    def _dominates(self, left: MethodScore, right: MethodScore) -> bool:
        eps = self.policy.dominance_epsilon
        l = left.quality.as_dict()
        r = right.quality.as_dict()
        no_worse = all(l[name] + eps >= r[name] for name in QualityVector.names())
        strictly_better = any(l[name] > r[name] + eps for name in QualityVector.names())
        return no_worse and strictly_better

    def annual(self, year: int, *, previous: AnnualFrontier | None = None) -> AnnualFrontier:
        methods = self.methods_known_by(year)
        eligible = [
            method
            for method in methods
            if method.evidence.conservative_strength >= self.policy.minimum_evidence_strength
        ]
        scores: dict[str, MethodScore] = {}
        unevaluated: list[str] = []
        hard_failed: list[str] = []
        for method in eligible:
            score = self.score(method.method_id, year)
            if score is None:
                unevaluated.append(method.method_id)
                continue
            if score.hard_failures and self.policy.hard_failure_is_disqualifying:
                hard_failed.append(method.method_id)
                continue
            scores[method.method_id] = score

        frontier: list[str] = []
        for method_id, score in sorted(scores.items()):
            dominated = any(
                other_id != method_id and self._dominates(other, score)
                for other_id, other in scores.items()
            )
            if not dominated:
                frontier.append(method_id)

        previous_ids = set(previous.pareto_method_ids) if previous is not None else set()
        current_ids = set(frontier)
        promoted = tuple(sorted(current_ids - previous_ids))
        retained = tuple(sorted(current_ids & previous_ids))
        removed = tuple(sorted(previous_ids - current_ids))
        payload = {
            "year": year,
            "eligible": [m.method_id for m in eligible],
            "evaluated": sorted(scores),
            "pareto": sorted(frontier),
            "promoted": promoted,
            "retained": retained,
            "removed": removed,
            "hard_failed": sorted(hard_failed),
            "unevaluated": sorted(unevaluated),
        }
        return AnnualFrontier(
            year=year,
            eligible_method_ids=tuple(payload["eligible"]),
            evaluated_method_ids=tuple(payload["evaluated"]),
            pareto_method_ids=tuple(payload["pareto"]),
            promoted_method_ids=promoted,
            retained_method_ids=retained,
            removed_method_ids=removed,
            hard_failed_method_ids=tuple(payload["hard_failed"]),
            unevaluated_method_ids=tuple(payload["unevaluated"]),
            fingerprint=stable_fingerprint(payload),
        )

    def walk(self, start_year: int, end_year: int) -> tuple[AnnualFrontier, ...]:
        if end_year < start_year:
            raise AgentContractError("end_year cannot precede start_year")
        previous = None
        rows: list[AnnualFrontier] = []
        for year in range(start_year, end_year + 1):
            current = self.annual(year, previous=previous)
            rows.append(current)
            previous = current
        return tuple(rows)

    def select_for_context(
        self,
        year: int,
        *,
        weights: Mapping[str, float],
        families: Sequence[MethodFamily] = (),
        limit: int = 8,
    ) -> tuple[MethodScore, ...]:
        required = {
            value if isinstance(value, MethodFamily) else MethodFamily(str(value))
            for value in families
        }
        frontier = self.annual(year)
        rows: list[MethodScore] = []
        for method_id in frontier.pareto_method_ids:
            method = self._methods[method_id]
            if required and not required.intersection(method.families):
                continue
            score = self.score(method_id, year, weights=weights)
            if score is not None:
                rows.append(score)
        rows.sort(
            key=lambda item: (
                item.scalar_score if item.scalar_score is not None else -1.0,
                item.evidence_strength,
                item.latest_evaluation_year,
                item.method_id,
            ),
            reverse=True,
        )
        return tuple(rows[: max(1, int(limit))])

    def compatible_pairs(self, year: int) -> tuple[tuple[str, str], ...]:
        """Return explicitly compatible/perpendicular frontier pairs.

        This does not automatically compose algorithms; it identifies research
        combinations that deserve a separate integration experiment.
        """
        frontier = self.annual(year)
        ids = set(frontier.pareto_method_ids)
        pairs: set[tuple[str, str]] = set()
        for method_id in ids:
            method = self._methods[method_id]
            for other in method.orthogonal_to:
                if other in ids and other != method_id:
                    pairs.add(tuple(sorted((method_id, other))))
        return tuple(sorted(pairs))

    def method(self, method_id: str) -> HistoricalMethod | None:
        return self._methods.get(str(method_id).casefold())

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "methods": [(key, value.fingerprint) for key, value in sorted(self._methods.items())],
                "evaluations": [(key, value.fingerprint) for key, value in sorted(self._evaluations.items())],
            }
        )


class HistoricalContextAdapter:
    """Expose the historical corpus as canonical CHRONICLE context."""

    source_tier = SourceTier.CHRONICLE
    source_provider = "scientific-lineage"

    def __init__(self, frontier: ChronologicalScientificFrontier, *, knowledge_year: int = 2026) -> None:
        self.frontier = frontier
        self.knowledge_year = int(knowledge_year)

    @staticmethod
    def _ref(method_id: str) -> str:
        return f"scientific-lineage:{method_id}"

    def _record(self, method: HistoricalMethod) -> DeepContextRecord:
        content = json_safe(
            {
                "method_id": method.method_id,
                "name": method.name,
                "introduced_year": method.introduced_year,
                "families": [family.value for family in method.families],
                "thesis": method.thesis,
                "assumptions": list(method.assumptions),
                "failure_modes": list(method.failure_modes),
                "parent_ids": list(method.parent_ids),
                "supersedes": list(method.supersedes),
                "orthogonal_to": list(method.orthogonal_to),
                "invariant_tags": list(method.invariant_tags),
                "references": [
                    {
                        "reference_id": ref.reference_id,
                        "title": ref.title,
                        "publication_year": ref.publication_year,
                        "locator": ref.locator,
                        "contribution": ref.contribution,
                        "limitations": ref.limitations,
                    }
                    for ref in method.references
                    if ref.publication_year <= self.knowledge_year
                ],
            }
        )
        import json
        text = json.dumps(content, sort_keys=True, ensure_ascii=False)
        evidence_strength = method.evidence.conservative_strength
        return DeepContextRecord(
            source_tier=self.source_tier,
            source_ref=self._ref(method.method_id),
            source_fingerprint=method.fingerprint,
            content=text,
            canonical=True,
            trust=max(0.05, min(1.0, evidence_strength)),
            confidence=max(0.05, min(1.0, evidence_strength)),
            salience=0.75,
            token_estimate=max(1, len(text) // 4),
            source_provider=self.source_provider,
            tags=tuple(family.value for family in method.families) + ("scientific-lineage",),
            metadata={
                "introduced_year": method.introduced_year,
                "knowledge_year": self.knowledge_year,
                "no_future_leakage": True,
            },
        )

    def fetch_refs(
        self,
        namespace_key: str,
        source_refs: Sequence[str],
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        wanted = {str(value) for value in source_refs}
        rows: list[DeepContextRecord] = []
        used = 0
        for method in self.frontier.methods_known_by(self.knowledge_year):
            if self._ref(method.method_id) not in wanted:
                continue
            record = self._record(method)
            if rows and used + record.token_estimate > max_tokens:
                continue
            rows.append(record)
            used += record.token_estimate
            if len(rows) >= max_records:
                break
        return tuple(rows)

    def search(
        self,
        namespace_key: str,
        query: str,
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        tokens = {token.casefold() for token in str(query).replace("/", " ").replace("-", " ").split() if token}
        candidates: list[tuple[int, HistoricalMethod]] = []
        for method in self.frontier.methods_known_by(self.knowledge_year):
            haystack = " ".join(
                (
                    method.name,
                    method.thesis,
                    " ".join(family.value for family in method.families),
                    " ".join(method.invariant_tags),
                )
            ).casefold()
            score = sum(1 for token in tokens if token in haystack)
            if score:
                candidates.append((score, method))
        candidates.sort(key=lambda item: (item[0], item[1].introduced_year, item[1].method_id), reverse=True)
        rows: list[DeepContextRecord] = []
        used = 0
        for _, method in candidates:
            record = self._record(method)
            if rows and used + record.token_estimate > max_tokens:
                continue
            rows.append(record)
            used += record.token_estimate
            if len(rows) >= max_records:
                break
        return tuple(rows)

    def index_cards(
        self,
        index: MemoryGameIndex,
        namespace_key: str,
        *,
        up_to_year: int | None = None,
    ) -> tuple[str, ...]:
        year = self.knowledge_year if up_to_year is None else min(int(up_to_year), self.knowledge_year)
        cards = []
        by_family: dict[MethodFamily, list[tuple[int, str]]] = {}
        for method in self.frontier.methods_known_by(year):
            record = self._record(method)
            card = index.index_source(
                namespace_key=namespace_key,
                source_tier=self.source_tier,
                source_ref=record.source_ref,
                source_fingerprint=record.source_fingerprint,
                source_provider=record.source_provider,
                cue=f"{method.name} {' '.join(f.value for f in method.families)} {method.thesis}",
                preview=record.content[:8192],
                kind=CardKind.FACT_CUE,
                salience=record.salience,
                trust=record.trust,
                confidence=record.confidence,
                tags=record.tags,
                metadata={
                    "canonical_source_required": True,
                    "introduced_year": method.introduced_year,
                    "scientific_lineage": True,
                },
            )
            cards.append(card.card_id)
            for family in method.families:
                by_family.setdefault(family, []).append((method.introduced_year, card.card_id))
        for values in by_family.values():
            ordered = [card_id for _, card_id in sorted(values)]
            if len(ordered) >= 2:
                index.link_sequence(ordered, strength=0.7, source="scientific-lineage")
        return tuple(cards)


def _reference(reference_id: str, title: str, year: int, locator: str, contribution: str, limitations: str = ""):
    return HistoricalReference(reference_id, title, year, locator, contribution, limitations)


def foundational_seed_methods() -> tuple[HistoricalMethod, ...]:
    """Small cross-era seed.  Hosts should bulk-ingest a much larger corpus."""

    return (
        HistoricalMethod(
            "bayes-1763",
            "Bayesian inverse probability",
            1763,
            (MethodFamily.PROBABILITY,),
            "Update uncertainty about a latent cause using evidence and prior uncertainty.",
            EvidenceProfile(formal_strength=0.95, empirical_strength=0.75, replication=0.95, external_validity=0.95, reproducibility=0.95, falsifiability=0.9),
            (_reference("bayes1763", "An Essay towards solving a Problem in the Doctrine of Chances", 1763, "Phil. Trans. 53", "foundational inverse-probability reasoning"),),
            assumptions=("probability model and prior are explicit enough to audit",),
            invariant_tags=("posterior-normalization", "conditioning"),
            orthogonal_to=("shannon-1948", "pearl-2000"),
        ),
        HistoricalMethod(
            "ebbinghaus-1885",
            "Experimental forgetting and relearning",
            1885,
            (MethodFamily.MEMORY,),
            "Measure retention, forgetting, savings and relearning as functions of delay and repetition.",
            EvidenceProfile(formal_strength=0.35, empirical_strength=0.9, replication=0.85, external_validity=0.6, reproducibility=0.85, falsifiability=0.95),
            (_reference("ebbinghaus1885", "Über das Gedächtnis", 1885, "Duncker & Humblot", "quantitative experimental study of memory and forgetting"),),
            failure_modes=("simple forgetting curves need not transfer unchanged across material, task, or individual",),
            invariant_tags=("retention-over-time", "relearning"),
        ),
        HistoricalMethod(
            "kolmogorov-1933",
            "Axiomatic probability",
            1933,
            (MethodFamily.PROBABILITY,),
            "Represent probability with a measure-theoretic axiom system.",
            EvidenceProfile(formal_strength=1.0, empirical_strength=0.5, replication=1.0, external_validity=1.0, reproducibility=1.0, falsifiability=0.65),
            (_reference("kolmogorov1933", "Grundbegriffe der Wahrscheinlichkeitsrechnung", 1933, "Springer", "axiomatization of probability"),),
            invariant_tags=("measure-normalization", "countable-additivity"),
            orthogonal_to=("bayes-1763",),
        ),
        HistoricalMethod(
            "turing-1936",
            "Computable procedures",
            1936,
            (MethodFamily.COMPILER, MethodFamily.SEMANTICS),
            "Separate an effective procedure from the particular machinery executing it.",
            EvidenceProfile(formal_strength=1.0, empirical_strength=0.4, replication=1.0, external_validity=1.0, reproducibility=1.0, falsifiability=0.8),
            (_reference("turing1936", "On Computable Numbers, with an Application to the Entscheidungsproblem", 1936, "Proc. London Math. Soc.", "formal model of effective computation"),),
            invariant_tags=("effective-computation",),
        ),
        HistoricalMethod(
            "shannon-1948",
            "Information entropy",
            1948,
            (MethodFamily.INFORMATION, MethodFamily.PROBABILITY),
            "Quantify uncertainty and information independently from semantic interpretation.",
            EvidenceProfile(formal_strength=1.0, empirical_strength=0.8, replication=1.0, external_validity=1.0, reproducibility=1.0, falsifiability=0.95),
            (_reference("shannon1948", "A Mathematical Theory of Communication", 1948, "Bell System Technical Journal", "entropy and channel-capacity framework"),),
            invariant_tags=("entropy", "information-units"),
            orthogonal_to=("bayes-1763", "kuleshov-2024"),
        ),
        HistoricalMethod(
            "bellman-1957",
            "Dynamic programming",
            1957,
            (MethodFamily.DECISION, MethodFamily.CONTROL),
            "Solve sequential decisions through recursively decomposed value functions.",
            EvidenceProfile(formal_strength=1.0, empirical_strength=0.85, replication=1.0, external_validity=0.95, reproducibility=1.0, falsifiability=0.95),
            (_reference("bellman1957", "Dynamic Programming", 1957, "Princeton University Press", "principle of optimality and recursive decision solution"),),
            invariant_tags=("bellman-recursion",),
            orthogonal_to=("bayes-1763", "pearl-2000"),
        ),
        HistoricalMethod(
            "hoare-1969",
            "Axiomatic program correctness",
            1969,
            (MethodFamily.VERIFICATION, MethodFamily.COMPILER),
            "State and prove precondition/postcondition obligations for program fragments.",
            EvidenceProfile(formal_strength=1.0, empirical_strength=0.55, replication=1.0, external_validity=0.95, reproducibility=1.0, falsifiability=0.85),
            (_reference("hoare1969", "An Axiomatic Basis for Computer Programming", 1969, "CACM 12(10)", "formal reasoning about program correctness"),),
            invariant_tags=("precondition", "postcondition", "invariant"),
            orthogonal_to=("abstract-interpretation-1977",),
        ),
        HistoricalMethod(
            "abstract-interpretation-1977",
            "Abstract interpretation",
            1977,
            (MethodFamily.PROGRAM_ANALYSIS, MethodFamily.VERIFICATION),
            "Soundly approximate concrete program semantics in an abstract domain.",
            EvidenceProfile(formal_strength=1.0, empirical_strength=0.75, replication=1.0, external_validity=0.95, reproducibility=0.95, falsifiability=0.9),
            (_reference("cousot1977", "Abstract Interpretation: A Unified Lattice Model for Static Analysis", 1977, "POPL", "sound semantic abstraction for static analysis"),),
            parent_ids=("hoare-1969",),
            invariant_tags=("sound-overapproximation", "fixpoint"),
        ),
        HistoricalMethod(
            "ssa-1991",
            "Static single assignment form",
            1991,
            (MethodFamily.COMPILER, MethodFamily.PROGRAM_ANALYSIS),
            "Give values single definitions and make dataflow joins explicit.",
            EvidenceProfile(formal_strength=0.9, empirical_strength=0.9, replication=1.0, external_validity=1.0, reproducibility=1.0, falsifiability=0.95),
            (_reference("cytron1991", "Efficiently Computing Static Single Assignment Form and the Control Dependence Graph", 1991, "TOPLAS 13(4)", "practical SSA construction and control dependence"),),
            invariant_tags=("single-definition", "explicit-dataflow"),
            orthogonal_to=("abstract-interpretation-1977",),
        ),
        HistoricalMethod(
            "mda-2004",
            "Mechanics-Dynamics-Aesthetics",
            2004,
            (MethodFamily.GAMES, MethodFamily.NARRATIVE),
            "Analyze games by separating designed mechanics, emergent dynamics, and player aesthetics.",
            EvidenceProfile(formal_strength=0.35, empirical_strength=0.4, replication=0.55, external_validity=0.7, reproducibility=0.65, falsifiability=0.45),
            (_reference("mda2004", "MDA: A Formal Approach to Game Design and Game Research", 2004, "AAAI WS-04-04-001", "cross-perspective game-design decomposition", "framework, not a calibrated predictive law"),),
            failure_modes=("descriptive decomposition can be mistaken for empirical prediction",),
            invariant_tags=("mechanics", "dynamics", "aesthetics"),
        ),
        HistoricalMethod(
            "conformal-2005",
            "Conformal prediction",
            2005,
            (MethodFamily.PROBABILITY, MethodFamily.LEARNING),
            "Construct prediction sets with finite-sample coverage guarantees under stated exchangeability conditions.",
            EvidenceProfile(formal_strength=0.98, empirical_strength=0.9, replication=0.95, external_validity=0.85, reproducibility=0.95, falsifiability=0.95),
            (_reference("vovk2005", "Algorithmic Learning in a Random World", 2005, "Springer", "conformal prediction framework"),),
            assumptions=("nominal finite-sample coverage requires the relevant exchangeability conditions",),
            invariant_tags=("coverage", "exchangeability"),
            orthogonal_to=("bayes-1763",),
        ),
        HistoricalMethod(
            "pearl-2000",
            "Structural causal modeling",
            2000,
            (MethodFamily.CAUSALITY, MethodFamily.PROBABILITY),
            "Represent interventions and counterfactual assumptions separately from observational conditioning.",
            EvidenceProfile(formal_strength=0.98, empirical_strength=0.85, replication=0.95, external_validity=0.9, reproducibility=0.95, falsifiability=0.9),
            (_reference("pearl2000", "Causality: Models, Reasoning, and Inference", 2000, "Cambridge University Press", "structural causal models, interventions, and counterfactual reasoning"),),
            assumptions=("causal graph and identification assumptions must be explicit",),
            invariant_tags=("observation-vs-intervention", "identification"),
            orthogonal_to=("bayes-1763", "bellman-1957"),
        ),
        HistoricalMethod(
            "kuleshov-2024",
            "Empirical contextual juxtaposition",
            2024,
            (MethodFamily.CINEMA, MethodFamily.SEMANTICS),
            "Adjacent emotional context can shift interpretation of an unchanged neutral face in a controlled face-scene-face paradigm.",
            EvidenceProfile(formal_strength=0.2, empirical_strength=0.9, replication=0.65, external_validity=0.65, reproducibility=0.75, falsifiability=0.95),
            (_reference("cao2024", "Reexamining the Kuleshov effect: Behavioral and neural evidence from authentic film experiments", 2024, "doi:10.1371/journal.pone.0308295", "behavioral and neural evidence for contextual framing in authentic-film sequences", "bounded paradigm; does not validate arbitrary symbolic readings"),),
            invariant_tags=("same-target-different-context", "contextual-framing"),
        ),
        HistoricalMethod(
            "ceptre-2023",
            "Formal executable game mechanics",
            2023,
            (MethodFamily.GAMES, MethodFamily.VERIFICATION),
            "Represent game mechanics with a formal executable rewriting system that can be simulated, queried and verified.",
            EvidenceProfile(formal_strength=0.95, empirical_strength=0.75, replication=0.7, external_validity=0.75, reproducibility=0.85, falsifiability=0.9),
            (_reference("ceptre2023", "Modeling Game Mechanics With Ceptre", 2023, "doi:10.1109/TG.2023.3292982", "formal game-mechanics modeling with simulation and verification"),),
            invariant_tags=("formal-mechanics", "executable-specification"),
            orthogonal_to=("mda-2004",),
        ),
        HistoricalMethod(
            "predictive-testing-2025",
            "Prediction-error account of retrieval practice",
            2025,
            (MethodFamily.MEMORY, MethodFamily.LEARNING, MethodFamily.RETRIEVAL),
            "Active retrieval can generate predictions and prediction errors that contribute to later memory benefit.",
            EvidenceProfile(formal_strength=0.55, empirical_strength=0.95, replication=0.7, external_validity=0.65, reproducibility=0.8, falsifiability=0.95),
            (_reference("chen2025", "Neural and computational evidence for a predictive learning account of the testing effect", 2025, "doi:10.1073/pnas.2506530122", "behavioral, computational and fMRI support for predictive-learning mechanisms in the testing effect", "mechanism remains a scientific account with scope limits; transfer beyond studied tasks requires testing"),),
            parent_ids=("ebbinghaus-1885",),
            invariant_tags=("active-retrieval", "prediction-error"),
        ),
    )


__all__ = [
    "AnnualFrontier",
    "ChronologicalScientificFrontier",
    "EvidenceProfile",
    "HistoricalContextAdapter",
    "HistoricalMethod",
    "HistoricalReference",
    "HistoricalSynthesisPolicy",
    "MethodEvaluation",
    "MethodFamily",
    "MethodScore",
    "QualityVector",
    "foundational_seed_methods",
]
