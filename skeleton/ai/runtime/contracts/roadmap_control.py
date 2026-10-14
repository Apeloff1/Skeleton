"""Canonical governed roadmap-control contracts for VOL-118.

Roadmap control is subordinate to canonical plan/build authorities. It records
which already-governed work is active in a roadmap revision, why a replan
occurred, and which exact architecture decision authorized any breadth-freeze
top-level scope addition.

Revisions are immutable snapshots. They must remain dependency-closed, bind
replan evidence to exact items, and cannot silently introduce hidden scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Iterable

ROADMAP_SCHEMA = "skeleton.contracts.roadmap_control.v1"
_MAX_ITEMS = 20_000
_MAX_DEPENDENCIES = 100_000
_MAX_REVISIONS = 10_000
_MAX_EVIDENCE = 100_000
_MAX_TEXT = 4_096
_MAX_TICK = 2_147_483_647
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RoadmapError(ValueError):
    """Roadmap-control state is malformed, contradictory, or unauthorized."""


class RoadmapEvidenceKind(str, Enum):
    BLOCKER = "blocker"
    ASSUMPTION = "assumption"
    RISK = "risk"
    ACCEPTANCE = "acceptance"


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise RoadmapError(f"{field} must be stable identifier")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RoadmapError(f"{field} must be lowercase sha256")
    return value


def _text(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _MAX_TEXT
    ):
        raise RoadmapError(f"{field} must be bounded canonical text")
    if any(ord(char) < 32 and char not in "\t" for char in value):
        raise RoadmapError(f"{field} contains control characters")
    return value


def _tick(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoadmapError(f"{field} must be nonnegative integer")
    if not 0 <= value <= _MAX_TICK:
        raise RoadmapError(f"{field} must be nonnegative integer")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RoadmapError("roadmap state must be deterministic JSON") from exc
    return sha256(raw).hexdigest()


def _ids(
    values: tuple[str, ...],
    *,
    field: str,
    required: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise RoadmapError(f"{field} must be tuple")
    if required and not values:
        raise RoadmapError(f"{field} must be non-empty")
    item_field = field[:-4] if field.endswith("_ids") else field
    normalized = tuple(_id(item, item_field) for item in values)
    if len(normalized) != len(set(normalized)):
        raise RoadmapError(f"duplicate {item_field}")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class RoadmapDependency:
    upstream_id: str
    downstream_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "upstream_id",
            _id(self.upstream_id, "upstream_id"),
        )
        object.__setattr__(
            self,
            "downstream_id",
            _id(self.downstream_id, "downstream_id"),
        )
        if self.upstream_id == self.downstream_id:
            raise RoadmapError("self dependency")

    @property
    def digest(self) -> str:
        return _digest(
            [
                ROADMAP_SCHEMA,
                self.upstream_id,
                self.downstream_id,
            ]
        )


@dataclass(frozen=True, slots=True)
class RoadmapItem:
    item_id: str
    work_package_id: str
    build_node_id: str
    risk_ids: tuple[str, ...]
    acceptance_gate_ids: tuple[str, ...]
    top_level_scope: bool = False
    architecture_decision_id: str | None = None

    def __post_init__(self) -> None:
        for field in ("item_id", "work_package_id", "build_node_id"):
            object.__setattr__(
                self,
                field,
                _id(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "risk_ids",
            _ids(self.risk_ids, field="risk_ids"),
        )
        object.__setattr__(
            self,
            "acceptance_gate_ids",
            _ids(
                self.acceptance_gate_ids,
                field="acceptance_gate_ids",
                required=True,
            ),
        )
        if not isinstance(self.top_level_scope, bool):
            raise RoadmapError("top_level_scope must be bool")
        if self.architecture_decision_id is not None:
            object.__setattr__(
                self,
                "architecture_decision_id",
                _id(
                    self.architecture_decision_id,
                    "architecture_decision_id",
                ),
            )
        if self.top_level_scope and self.architecture_decision_id is None:
            raise RoadmapError(
                "breadth-freeze scope addition requires architecture decision"
            )

    @property
    def digest(self) -> str:
        return _digest(
            [
                ROADMAP_SCHEMA,
                self.item_id,
                self.work_package_id,
                self.build_node_id,
                list(self.risk_ids),
                list(self.acceptance_gate_ids),
                self.top_level_scope,
                self.architecture_decision_id,
            ]
        )


@dataclass(frozen=True, slots=True)
class RoadmapEvidence:
    evidence_id: str
    item_id: str
    item_digest: str
    kind: RoadmapEvidenceKind
    artifact_digest: str
    observed_tick: int
    active: bool
    producer_id: str

    def __post_init__(self) -> None:
        for field in ("evidence_id", "item_id", "producer_id"):
            object.__setattr__(
                self,
                field,
                _id(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "item_digest",
            _sha(self.item_digest, "item_digest"),
        )
        if not isinstance(self.kind, RoadmapEvidenceKind):
            raise RoadmapError("kind must be RoadmapEvidenceKind")
        object.__setattr__(
            self,
            "artifact_digest",
            _sha(self.artifact_digest, "artifact_digest"),
        )
        object.__setattr__(
            self,
            "observed_tick",
            _tick(self.observed_tick, "observed_tick"),
        )
        if not isinstance(self.active, bool):
            raise RoadmapError("active must be bool")
        object.__setattr__(
            self,
            "producer_id",
            _id(self.producer_id, "producer_id"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                ROADMAP_SCHEMA,
                self.evidence_id,
                self.item_id,
                self.item_digest,
                self.kind.value,
                self.artifact_digest,
                self.observed_tick,
                self.active,
                self.producer_id,
            ]
        )


@dataclass(frozen=True, slots=True)
class RoadmapArchitectureDecision:
    decision_id: str
    item_id: str
    item_digest: str
    evidence_digest: str
    approved: bool
    approver_id: str
    observed_tick: int

    def __post_init__(self) -> None:
        for field in ("decision_id", "item_id", "approver_id"):
            object.__setattr__(
                self,
                field,
                _id(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "item_digest",
            _sha(self.item_digest, "item_digest"),
        )
        object.__setattr__(
            self,
            "evidence_digest",
            _sha(self.evidence_digest, "evidence_digest"),
        )
        if not isinstance(self.approved, bool):
            raise RoadmapError("approved must be bool")
        object.__setattr__(
            self,
            "observed_tick",
            _tick(self.observed_tick, "observed_tick"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                ROADMAP_SCHEMA,
                self.decision_id,
                self.item_id,
                self.item_digest,
                self.evidence_digest,
                self.approved,
                self.approver_id,
                self.observed_tick,
            ]
        )


@dataclass(frozen=True, slots=True)
class RoadmapRevision:
    revision_id: str
    parent_revision_id: str | None
    assumption_digest: str
    rationale: str
    item_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()
    architecture_decision_ids: tuple[str, ...] = ()
    author_id: str = "OWNER.ROADMAP"
    created_tick: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "revision_id",
            _id(self.revision_id, "revision_id"),
        )
        if self.parent_revision_id is not None:
            object.__setattr__(
                self,
                "parent_revision_id",
                _id(self.parent_revision_id, "parent_revision_id"),
            )
        if self.parent_revision_id == self.revision_id:
            raise RoadmapError("revision cannot parent itself")
        object.__setattr__(
            self,
            "assumption_digest",
            _sha(self.assumption_digest, "assumption_digest"),
        )
        object.__setattr__(
            self,
            "rationale",
            _text(self.rationale, "rationale"),
        )
        object.__setattr__(
            self,
            "item_ids",
            _ids(
                self.item_ids,
                field="item_ids",
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "evidence_ids",
            _ids(self.evidence_ids, field="evidence_ids"),
        )
        object.__setattr__(
            self,
            "architecture_decision_ids",
            _ids(
                self.architecture_decision_ids,
                field="architecture_decision_ids",
            ),
        )
        object.__setattr__(
            self,
            "author_id",
            _id(self.author_id, "author_id"),
        )
        object.__setattr__(
            self,
            "created_tick",
            _tick(self.created_tick, "created_tick"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                ROADMAP_SCHEMA,
                self.revision_id,
                self.parent_revision_id,
                self.assumption_digest,
                self.rationale,
                list(self.item_ids),
                list(self.evidence_ids),
                list(self.architecture_decision_ids),
                self.author_id,
                self.created_tick,
            ]
        )


@dataclass(frozen=True, slots=True)
class RoadmapRevisionDiff:
    revision_id: str
    parent_revision_id: str | None
    added_item_ids: tuple[str, ...]
    removed_item_ids: tuple[str, ...]
    top_level_addition_ids: tuple[str, ...]
    assumption_changed: bool
    evidence_ids: tuple[str, ...]
    architecture_decision_ids: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(
            self.added_item_ids
            or self.removed_item_ids
            or self.assumption_changed
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                ROADMAP_SCHEMA,
                self.revision_id,
                self.parent_revision_id,
                list(self.added_item_ids),
                list(self.removed_item_ids),
                list(self.top_level_addition_ids),
                self.assumption_changed,
                list(self.evidence_ids),
                list(self.architecture_decision_ids),
            ]
        )


@dataclass(frozen=True, slots=True)
class RoadmapSnapshot:
    control_digest: str
    latest_revision_id: str | None
    active_item_ids: tuple[str, ...]
    revision_digests: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _digest(
            [
                ROADMAP_SCHEMA,
                self.control_digest,
                self.latest_revision_id,
                list(self.active_item_ids),
                list(self.revision_digests),
            ]
        )


class RoadmapControl:
    """Governed roadmap snapshots and evidence-bound replanning."""

    def __init__(
        self,
        items: Iterable[RoadmapItem],
        dependencies: Iterable[RoadmapDependency] = (),
        evidence: Iterable[RoadmapEvidence] = (),
        architecture_decisions: Iterable[RoadmapArchitectureDecision] = (),
    ) -> None:
        materialized_items = tuple(items)
        materialized_dependencies = tuple(dependencies)
        materialized_evidence = tuple(evidence)
        materialized_decisions = tuple(architecture_decisions)

        if not materialized_items:
            raise RoadmapError("items must be non-empty")
        if len(materialized_items) > _MAX_ITEMS:
            raise RoadmapError("roadmap item count exceeds safety bound")
        if len(materialized_dependencies) > _MAX_DEPENDENCIES:
            raise RoadmapError("dependency count exceeds safety bound")
        if len(materialized_evidence) > _MAX_EVIDENCE:
            raise RoadmapError("evidence count exceeds safety bound")

        if any(
            not isinstance(item, RoadmapItem)
            for item in materialized_items
        ):
            raise TypeError("items must contain RoadmapItem")
        if any(
            not isinstance(item, RoadmapDependency)
            for item in materialized_dependencies
        ):
            raise TypeError(
                "dependencies must contain RoadmapDependency"
            )
        if any(
            not isinstance(item, RoadmapEvidence)
            for item in materialized_evidence
        ):
            raise TypeError("evidence must contain RoadmapEvidence")
        if any(
            not isinstance(item, RoadmapArchitectureDecision)
            for item in materialized_decisions
        ):
            raise TypeError(
                "architecture_decisions must contain RoadmapArchitectureDecision"
            )

        item_ids = [item.item_id for item in materialized_items]
        if len(item_ids) != len(set(item_ids)):
            raise RoadmapError("duplicate roadmap item")
        dependency_ids = [
            (item.upstream_id, item.downstream_id)
            for item in materialized_dependencies
        ]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise RoadmapError("duplicate roadmap dependency")
        evidence_ids = [item.evidence_id for item in materialized_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise RoadmapError("duplicate roadmap evidence")
        decision_ids = [
            item.decision_id for item in materialized_decisions
        ]
        if len(decision_ids) != len(set(decision_ids)):
            raise RoadmapError("duplicate roadmap architecture decision")

        self.items = {
            item.item_id: item
            for item in sorted(
                materialized_items,
                key=lambda item: item.item_id,
            )
        }
        self.dependencies = tuple(
            sorted(
                materialized_dependencies,
                key=lambda item: (
                    item.upstream_id,
                    item.downstream_id,
                ),
            )
        )
        self.evidence = {
            item.evidence_id: item
            for item in sorted(
                materialized_evidence,
                key=lambda item: item.evidence_id,
            )
        }
        self.architecture_decisions = {
            item.decision_id: item
            for item in sorted(
                materialized_decisions,
                key=lambda item: item.decision_id,
            )
        }
        self.revisions: dict[str, RoadmapRevision] = {}

        for dependency in self.dependencies:
            if (
                dependency.upstream_id not in self.items
                or dependency.downstream_id not in self.items
            ):
                raise RoadmapError("unknown roadmap dependency")
        self._reject_cycles()

        for item in self.evidence.values():
            subject = self._item(item.item_id)
            if item.item_digest != subject.digest:
                raise RoadmapError("evidence item digest mismatch")

        for decision in self.architecture_decisions.values():
            subject = self._item(decision.item_id)
            if decision.item_digest != subject.digest:
                raise RoadmapError(
                    "architecture decision item digest mismatch"
                )
            if subject.architecture_decision_id != decision.decision_id:
                raise RoadmapError(
                    "architecture decision identity mismatch"
                )

    def _item(self, item_id: str) -> RoadmapItem:
        item_id = _id(item_id, "item_id")
        try:
            return self.items[item_id]
        except KeyError as exc:
            raise RoadmapError("unknown roadmap item") from exc

    def _reject_cycles(self) -> None:
        edges = {item_id: set() for item_id in self.items}
        for dependency in self.dependencies:
            edges[dependency.upstream_id].add(
                dependency.downstream_id
            )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(item_id: str) -> None:
            if item_id in visited:
                return
            if item_id in visiting:
                raise RoadmapError("roadmap dependency cycle")
            visiting.add(item_id)
            for child in sorted(edges[item_id]):
                visit(child)
            visiting.remove(item_id)
            visited.add(item_id)

        for item_id in sorted(edges):
            visit(item_id)

    @property
    def control_digest(self) -> str:
        return _digest(
            [
                ROADMAP_SCHEMA,
                [item.digest for item in self.items.values()],
                [item.digest for item in self.dependencies],
                [item.digest for item in self.evidence.values()],
                [
                    item.digest
                    for item in self.architecture_decisions.values()
                ],
            ]
        )

    def topological_order(
        self,
        item_ids: Iterable[str] | None = None,
    ) -> tuple[str, ...]:
        if item_ids is None:
            selected = set(self.items)
        else:
            selected = {
                _id(item_id, "item_id") for item_id in item_ids
            }
            unknown = selected - set(self.items)
            if unknown:
                raise RoadmapError("unknown roadmap item")

        indegree = {item_id: 0 for item_id in selected}
        adjacency = {item_id: set() for item_id in selected}
        for dependency in self.dependencies:
            if (
                dependency.upstream_id in selected
                and dependency.downstream_id in selected
            ):
                adjacency[dependency.upstream_id].add(
                    dependency.downstream_id
                )
                indegree[dependency.downstream_id] += 1

        ready = sorted(
            item_id for item_id, degree in indegree.items() if degree == 0
        )
        ordered: list[str] = []
        while ready:
            item_id = ready.pop(0)
            ordered.append(item_id)
            for child in sorted(adjacency[item_id]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort()

        if len(ordered) != len(selected):
            raise RoadmapError("roadmap dependency cycle")
        return tuple(ordered)

    def _validate_dependency_closure(
        self,
        item_ids: tuple[str, ...],
    ) -> None:
        active = set(item_ids)
        missing: list[str] = []
        for dependency in self.dependencies:
            if (
                dependency.downstream_id in active
                and dependency.upstream_id not in active
            ):
                missing.append(
                    f"{dependency.downstream_id}->{dependency.upstream_id}"
                )
        if missing:
            raise RoadmapError(
                "revision drops required upstream dependency: "
                + ",".join(sorted(missing))
            )

    def diff(self, revision: RoadmapRevision) -> RoadmapRevisionDiff:
        if not isinstance(revision, RoadmapRevision):
            raise TypeError("revision must be RoadmapRevision")
        if revision.parent_revision_id is None:
            parent_items: set[str] = set()
            parent_assumption = None
        else:
            try:
                parent = self.revisions[revision.parent_revision_id]
            except KeyError as exc:
                raise RoadmapError("unknown revision parent") from exc
            parent_items = set(parent.item_ids)
            parent_assumption = parent.assumption_digest

        current_items = set(revision.item_ids)
        added = tuple(sorted(current_items - parent_items))
        removed = tuple(sorted(parent_items - current_items))
        top_level = tuple(
            item_id
            for item_id in added
            if self.items[item_id].top_level_scope
        )
        return RoadmapRevisionDiff(
            revision_id=revision.revision_id,
            parent_revision_id=revision.parent_revision_id,
            added_item_ids=added,
            removed_item_ids=removed,
            top_level_addition_ids=top_level,
            assumption_changed=(
                parent_assumption is not None
                and revision.assumption_digest != parent_assumption
            ),
            evidence_ids=revision.evidence_ids,
            architecture_decision_ids=revision.architecture_decision_ids,
        )

    def _validate_revision_evidence(
        self,
        revision: RoadmapRevision,
        diff: RoadmapRevisionDiff,
    ) -> None:
        selected: list[RoadmapEvidence] = []
        for evidence_id in revision.evidence_ids:
            try:
                item = self.evidence[evidence_id]
            except KeyError as exc:
                raise RoadmapError(
                    "revision references unknown roadmap evidence"
                ) from exc
            if item.observed_tick > revision.created_tick:
                raise RoadmapError(
                    "revision references future roadmap evidence"
                )
            if not item.active:
                raise RoadmapError(
                    "revision references inactive roadmap evidence"
                )
            selected.append(item)

        if revision.parent_revision_id is not None and diff.changed:
            justifying = {
                RoadmapEvidenceKind.BLOCKER,
                RoadmapEvidenceKind.ASSUMPTION,
                RoadmapEvidenceKind.RISK,
            }
            if not any(item.kind in justifying for item in selected):
                raise RoadmapError(
                    "changed revision requires blocker/assumption/risk evidence"
                )

        changed_items = set(diff.added_item_ids) | set(diff.removed_item_ids)
        if changed_items and selected:
            referenced_items = {item.item_id for item in selected}
            if not (changed_items & referenced_items):
                raise RoadmapError(
                    "replan evidence does not bind changed roadmap scope"
                )

    def _validate_scope_decisions(
        self,
        revision: RoadmapRevision,
        diff: RoadmapRevisionDiff,
    ) -> None:
        selected: dict[str, RoadmapArchitectureDecision] = {}
        for decision_id in revision.architecture_decision_ids:
            try:
                decision = self.architecture_decisions[decision_id]
            except KeyError as exc:
                raise RoadmapError(
                    "revision references unknown architecture decision"
                ) from exc
            if decision.observed_tick > revision.created_tick:
                raise RoadmapError(
                    "revision references future architecture decision"
                )
            if not decision.approved:
                raise RoadmapError(
                    "revision references rejected architecture decision"
                )
            selected[decision.decision_id] = decision

        for item_id in diff.top_level_addition_ids:
            item = self.items[item_id]
            decision_id = item.architecture_decision_id
            assert decision_id is not None
            decision = selected.get(decision_id)
            if decision is None:
                raise RoadmapError(
                    "top-level scope addition missing exact architecture decision"
                )
            if decision.item_id != item_id:
                raise RoadmapError(
                    "architecture decision scope item mismatch"
                )
            if decision.item_digest != item.digest:
                raise RoadmapError(
                    "architecture decision scope revision mismatch"
                )

    def add_revision(
        self,
        revision: RoadmapRevision,
    ) -> RoadmapRevision:
        if not isinstance(revision, RoadmapRevision):
            raise RoadmapError("revision must be RoadmapRevision")
        if len(self.revisions) >= _MAX_REVISIONS:
            raise RoadmapError("revision count exceeds safety bound")
        if revision.revision_id in self.revisions:
            raise RoadmapError("duplicate roadmap revision")

        unknown = set(revision.item_ids) - set(self.items)
        if unknown:
            raise RoadmapError("revision references unknown item")

        if revision.parent_revision_id is None:
            if self.revisions:
                raise RoadmapError("only first revision may be root")
        else:
            if revision.parent_revision_id not in self.revisions:
                raise RoadmapError("unknown revision parent")
            parent = self.revisions[revision.parent_revision_id]
            if revision.created_tick < parent.created_tick:
                raise RoadmapError(
                    "revision chronology predates parent"
                )

        self._validate_dependency_closure(revision.item_ids)
        revision_diff = self.diff(revision)
        self._validate_revision_evidence(revision, revision_diff)
        self._validate_scope_decisions(revision, revision_diff)

        self.revisions[revision.revision_id] = revision
        return revision

    @property
    def latest_revision(self) -> RoadmapRevision | None:
        if not self.revisions:
            return None
        children = {
            revision.parent_revision_id
            for revision in self.revisions.values()
            if revision.parent_revision_id is not None
        }
        tips = [
            revision
            for revision in self.revisions.values()
            if revision.revision_id not in children
        ]
        if len(tips) != 1:
            raise RoadmapError("roadmap revision history has multiple tips")
        return tips[0]

    def snapshot(self) -> RoadmapSnapshot:
        latest = self.latest_revision
        return RoadmapSnapshot(
            control_digest=self.control_digest,
            latest_revision_id=(
                latest.revision_id if latest is not None else None
            ),
            active_item_ids=(
                latest.item_ids if latest is not None else ()
            ),
            revision_digests=tuple(
                self.revisions[revision_id].digest
                for revision_id in sorted(self.revisions)
            ),
        )


__all__ = [
    "ROADMAP_SCHEMA",
    "RoadmapArchitectureDecision",
    "RoadmapControl",
    "RoadmapDependency",
    "RoadmapError",
    "RoadmapEvidence",
    "RoadmapEvidenceKind",
    "RoadmapItem",
    "RoadmapRevision",
    "RoadmapRevisionDiff",
    "RoadmapSnapshot",
]
