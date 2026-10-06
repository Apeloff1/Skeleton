"""Critical long-horizon resilience primitives for the AI game-builder forge."""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, Mapping, Sequence

from .contracts import canonical_digest


class ResilienceError(RuntimeError):
    pass


def _stable_id(value: str, label: str) -> str:
    value = str(value).strip()
    if not value:
        raise ValueError(f"{label} must be non-empty")
    return value


def _stable_digest(value: str, label: str) -> str:
    value = _stable_id(value, label)
    if len(value) < 16:
        raise ValueError(f"{label} must be a stable digest")
    return value


def _feature_vector(values: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    if not values:
        raise ValueError("novelty feature vector cannot be empty")
    rows: list[tuple[str, float]] = []
    for key in sorted(values):
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("novelty feature values must be numeric")
        score = float(value)
        if not 0.0 <= score <= 1.0:
            raise ValueError("novelty feature values must be within [0,1]")
        rows.append((_stable_id(key, "feature name"), score))
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class NoveltyRecord:
    candidate_digest: str
    quality_score: float
    features: tuple[tuple[str, float], ...]

    @classmethod
    def create(
        cls,
        *,
        candidate_digest: str,
        quality_score: float,
        features: Mapping[str, float],
    ) -> "NoveltyRecord":
        _stable_digest(candidate_digest, "candidate_digest")
        if isinstance(quality_score, bool) or not isinstance(quality_score, (int, float)):
            raise ValueError("quality_score must be numeric")
        score = float(quality_score)
        if not 0.0 <= score <= 1.0:
            raise ValueError("quality_score must be within [0,1]")
        return cls(candidate_digest, score, _feature_vector(features))

    @property
    def feature_map(self) -> dict[str, float]:
        return dict(self.features)


class NoveltyReservoir:
    """Bounded set of strong, mutually distinct candidate alternatives."""

    def __init__(self, *, capacity: int = 16, minimum_distance: float = 0.15) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 2:
            raise ValueError("capacity must be an integer >= 2")
        if not 0.0 <= minimum_distance <= 1.0:
            raise ValueError("minimum_distance must be within [0,1]")
        self.capacity = capacity
        self.minimum_distance = float(minimum_distance)
        self._records: dict[str, NoveltyRecord] = {}

    @staticmethod
    def distance(left: NoveltyRecord, right: NoveltyRecord) -> float:
        lmap, rmap = left.feature_map, right.feature_map
        keys = tuple(sorted(set(lmap) | set(rmap)))
        if not keys:
            return 0.0
        square = sum((lmap.get(k, 0.0) - rmap.get(k, 0.0)) ** 2 for k in keys)
        # Normalize Euclidean distance into [0,1] for features individually in [0,1].
        return sqrt(square / len(keys))

    def nearest_distance(self, record: NoveltyRecord) -> float:
        if not self._records:
            return 1.0
        return min(self.distance(record, existing) for existing in self._records.values())

    def admit(self, record: NoveltyRecord) -> bool:
        existing = self._records.get(record.candidate_digest)
        if existing is not None:
            if existing != record:
                raise ResilienceError("candidate novelty identity reused with different payload")
            return False
        if self._records and self.nearest_distance(record) < self.minimum_distance:
            weakest = min(
                self._records.values(),
                key=lambda item: (item.quality_score, item.candidate_digest),
            )
            if record.quality_score <= weakest.quality_score:
                return False
        self._records[record.candidate_digest] = record
        while len(self._records) > self.capacity:
            victim = min(
                self._records.values(),
                key=lambda item: (item.quality_score, item.candidate_digest),
            )
            del self._records[victim.candidate_digest]
        return record.candidate_digest in self._records

    @property
    def records(self) -> tuple[NoveltyRecord, ...]:
        return tuple(
            sorted(
                self._records.values(),
                key=lambda item: (-item.quality_score, item.candidate_digest),
            )
        )

    def mode_collapse_risk(self) -> bool:
        rows = list(self._records.values())
        if len(rows) < 3:
            return False
        distances = [
            self.distance(rows[i], rows[j])
            for i in range(len(rows))
            for j in range(i + 1, len(rows))
        ]
        return bool(distances) and sum(distances) / len(distances) < self.minimum_distance


@dataclass(frozen=True, slots=True)
class Objection:
    objection_id: str
    artifact_digest: str
    evidence_digest: str
    summary: str
    severity: int
    dependency_ids: tuple[str, ...] = ()
    resolved_by_digest: str | None = None

    def __post_init__(self) -> None:
        _stable_id(self.objection_id, "objection_id")
        _stable_digest(self.artifact_digest, "artifact_digest")
        _stable_digest(self.evidence_digest, "evidence_digest")
        _stable_id(self.summary, "summary")
        if self.severity not in (1, 2, 4, 8):
            raise ValueError("severity must be one of 1,2,4,8")
        if len(self.dependency_ids) != len(set(self.dependency_ids)):
            raise ValueError("objection dependency ids must be unique")
        if self.resolved_by_digest is not None:
            _stable_digest(self.resolved_by_digest, "resolved_by_digest")

    @property
    def unresolved(self) -> bool:
        return self.resolved_by_digest is None


class DissentLedger:
    """Durable objections that cannot disappear merely because a candidate lost."""

    def __init__(self) -> None:
        self._items: dict[str, Objection] = {}

    def add(self, objection: Objection) -> None:
        if objection.objection_id in self._items:
            raise ResilienceError("duplicate objection identity")
        self._items[objection.objection_id] = objection

    def resolve(self, objection_id: str, *, resolution_digest: str) -> Objection:
        item = self._items.get(objection_id)
        if item is None:
            raise ResilienceError("unknown objection identity")
        if not item.unresolved:
            raise ResilienceError("objection already resolved")
        resolved = Objection(
            objection_id=item.objection_id,
            artifact_digest=item.artifact_digest,
            evidence_digest=item.evidence_digest,
            summary=item.summary,
            severity=item.severity,
            dependency_ids=item.dependency_ids,
            resolved_by_digest=_stable_digest(resolution_digest, "resolution_digest"),
        )
        self._items[objection_id] = resolved
        return resolved

    def blockers_for(
        self,
        *,
        artifact_digest: str,
        changed_dependency_ids: Iterable[str] = (),
        minimum_severity: int = 4,
    ) -> tuple[Objection, ...]:
        changed = set(changed_dependency_ids)
        return tuple(
            item
            for item in sorted(self._items.values(), key=lambda row: row.objection_id)
            if item.unresolved
            and item.severity >= minimum_severity
            and (
                item.artifact_digest == artifact_digest
                or bool(changed.intersection(item.dependency_ids))
            )
        )

    def snapshot(self) -> dict[str, object]:
        rows = [
            {
                "artifact_digest": item.artifact_digest,
                "dependency_ids": list(item.dependency_ids),
                "evidence_digest": item.evidence_digest,
                "objection_id": item.objection_id,
                "resolved_by_digest": item.resolved_by_digest,
                "severity": item.severity,
                "summary": item.summary,
            }
            for item in sorted(self._items.values(), key=lambda row: row.objection_id)
        ]
        core = {"items": rows, "schema": "skeleton.ai_game_builder.dissent.v1"}
        return {**core, "digest": canonical_digest(core)}


class ImpactGraph:
    """Deterministic forward/reverse dependency graph for validation blast radius."""

    def __init__(self) -> None:
        self._deps: dict[str, set[str]] = {}

    def add_node(self, node_id: str, *, depends_on: Iterable[str] = ()) -> None:
        node_id = _stable_id(node_id, "node_id")
        if node_id in self._deps:
            raise ResilienceError("duplicate impact node")
        deps = {_stable_id(dep, "dependency") for dep in depends_on}
        if node_id in deps:
            raise ResilienceError("impact node cannot depend on itself")
        missing = deps - set(self._deps)
        if missing:
            raise ResilienceError(f"unknown impact dependencies: {sorted(missing)}")
        self._deps[node_id] = deps
        if self._cycle_exists():
            del self._deps[node_id]
            raise ResilienceError("impact graph cycle detected")

    def _cycle_exists(self) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for dep in self._deps[node]:
                if visit(dep):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in self._deps)

    def blast_radius(self, changed: Iterable[str]) -> tuple[str, ...]:
        affected = {_stable_id(node, "changed node") for node in changed}
        unknown = affected - set(self._deps)
        if unknown:
            raise ResilienceError(f"unknown changed nodes: {sorted(unknown)}")
        progress = True
        while progress:
            progress = False
            for node, deps in self._deps.items():
                if node not in affected and deps.intersection(affected):
                    affected.add(node)
                    progress = True
        return tuple(sorted(affected))

    @staticmethod
    def calibration(
        predicted: Sequence[str],
        observed: Sequence[str],
    ) -> dict[str, float]:
        p, o = set(predicted), set(observed)
        tp = len(p & o)
        precision = tp / len(p) if p else (1.0 if not o else 0.0)
        recall = tp / len(o) if o else 1.0
        return {"precision": precision, "recall": recall}


@dataclass(frozen=True, slots=True)
class Invariant:
    invariant_id: str
    scope: str
    expression: str
    source_pillar: str
    severity: int
    inherited_by: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, label in (
            (self.invariant_id, "invariant_id"),
            (self.scope, "scope"),
            (self.expression, "expression"),
            (self.source_pillar, "source_pillar"),
        ):
            _stable_id(value, label)
        if self.severity not in (1, 2, 4, 8):
            raise ValueError("invariant severity must be one of 1,2,4,8")


class InvariantRegistry:
    """Versionable cross-granularity invariant set with conflict detection."""

    def __init__(self) -> None:
        self._items: dict[str, Invariant] = {}

    def add(self, invariant: Invariant) -> None:
        if invariant.invariant_id in self._items:
            raise ResilienceError("duplicate invariant identity")
        for other in self._items.values():
            same_scope = other.scope == invariant.scope
            same_expression = other.expression == invariant.expression
            if same_scope and same_expression and other.source_pillar != invariant.source_pillar:
                raise ResilienceError("ambiguous duplicate invariant from different pillars")
        self._items[invariant.invariant_id] = invariant

    def applicable(self, target_id: str) -> tuple[Invariant, ...]:
        target_id = _stable_id(target_id, "target_id")
        return tuple(
            item
            for item in sorted(self._items.values(), key=lambda row: row.invariant_id)
            if not item.inherited_by or target_id in item.inherited_by
        )

    def digest(self) -> str:
        return canonical_digest(
            [
                {
                    "expression": item.expression,
                    "inherited_by": list(item.inherited_by),
                    "invariant_id": item.invariant_id,
                    "scope": item.scope,
                    "severity": item.severity,
                    "source_pillar": item.source_pillar,
                }
                for item in sorted(self._items.values(), key=lambda row: row.invariant_id)
            ]
        )
