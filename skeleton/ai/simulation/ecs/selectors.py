"""Composable deterministic selection over ECS, tags, and partitions.

The low-level query engine filters component presence and field predicates.
``SelectionEngine`` adds world-facing constraints without duplicating state:
entity ids are first produced by ``QueryEngine`` and then intersected with
optional tag and partition views using stable lexical ordering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .canonical import digest
from .errors import QueryError, ValidationError
from .partitions import WorldPartitionIndex
from .query import FieldPredicate, QueryEngine, QuerySpec
from .relations import RelationGraph
from .store import EntityStore

MAX_SELECTOR_TAGS = 64
MAX_SELECTOR_PARTITIONS = 64


@dataclass(frozen=True)
class SelectorSpec:
    all_components: tuple[str, ...] = ()
    any_components: tuple[str, ...] = ()
    no_components: tuple[str, ...] = ()
    predicates: tuple[FieldPredicate, ...] = ()
    all_tags: tuple[str, ...] = ()
    any_tags: tuple[str, ...] = ()
    no_tags: tuple[str, ...] = ()
    partitions: tuple[str, ...] = ()
    limit: int = 100_000
    offset: int = 0

    def __post_init__(self) -> None:
        for name in (
            "all_components",
            "any_components",
            "no_components",
            "all_tags",
            "any_tags",
            "no_tags",
            "partitions",
        ):
            values = tuple(sorted(set(getattr(self, name))))
            if any(not isinstance(value, str) or not value for value in values):
                raise QueryError(f"selector {name} values must be non-empty text")
            object.__setattr__(self, name, values)
        if len(self.all_tags) > MAX_SELECTOR_TAGS:
            raise QueryError("too many required selector tags")
        if len(self.any_tags) > MAX_SELECTOR_TAGS:
            raise QueryError("too many optional selector tags")
        if len(self.no_tags) > MAX_SELECTOR_TAGS:
            raise QueryError("too many excluded selector tags")
        if len(self.partitions) > MAX_SELECTOR_PARTITIONS:
            raise QueryError("too many selector partitions")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit < 0:
            raise QueryError("selector limit must be non-negative integer")
        if isinstance(self.offset, bool) or not isinstance(self.offset, int) or self.offset < 0:
            raise QueryError("selector offset must be non-negative integer")
        object.__setattr__(self, "predicates", tuple(self.predicates))

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.ecs.selector_spec.v1",
                "all_components": self.all_components,
                "any_components": self.any_components,
                "no_components": self.no_components,
                "predicates": [predicate.__dict__ for predicate in self.predicates],
                "all_tags": self.all_tags,
                "any_tags": self.any_tags,
                "no_tags": self.no_tags,
                "partitions": self.partitions,
                "limit": self.limit,
                "offset": self.offset,
            }
        )


@dataclass(frozen=True)
class SelectionResult:
    entity_ids: tuple[str, ...]
    total_before_window: int
    selector_fingerprint: str
    store_digest: str
    result_digest: str

    @property
    def count(self) -> int:
        return len(self.entity_ids)


class SelectionEngine:
    def __init__(
        self,
        store: EntityStore,
        *,
        relations: RelationGraph | None = None,
        partitions: WorldPartitionIndex | None = None,
    ) -> None:
        if not isinstance(store, EntityStore):
            raise ValidationError("SelectionEngine requires EntityStore")
        if relations is not None and relations.store is not store:
            raise ValidationError("relation graph must reference selector store")
        if partitions is not None and partitions.store is not store:
            raise ValidationError("partition index must reference selector store")
        self.store = store
        self.relations = relations
        self.partitions = partitions

    def _component_candidates(self, spec: SelectorSpec) -> set[str]:
        query = QuerySpec(
            all_of=spec.all_components,
            any_of=spec.any_components,
            none_of=spec.no_components,
            predicates=spec.predicates,
            limit=100_000,
            offset=0,
        )
        return set(QueryEngine(self.store).ids(query))

    def _tag_candidates(self, spec: SelectorSpec) -> set[str] | None:
        if not (spec.all_tags or spec.any_tags or spec.no_tags):
            return None
        if self.relations is None:
            raise QueryError("selector tag constraints require RelationGraph")
        candidates = set(self.store.entity_ids())
        for tag in spec.all_tags:
            candidates &= set(self.relations.entities_with_tag(tag))
        if spec.any_tags:
            any_ids: set[str] = set()
            for tag in spec.any_tags:
                any_ids.update(self.relations.entities_with_tag(tag))
            candidates &= any_ids
        for tag in spec.no_tags:
            candidates -= set(self.relations.entities_with_tag(tag))
        return candidates

    def _partition_candidates(self, spec: SelectorSpec) -> set[str] | None:
        if not spec.partitions:
            return None
        if self.partitions is None:
            raise QueryError("selector partition constraints require WorldPartitionIndex")
        candidates: set[str] = set()
        for partition_id in spec.partitions:
            candidates.update(self.partitions.entities(partition_id))
        return candidates

    def select(self, spec: SelectorSpec) -> SelectionResult:
        if not isinstance(spec, SelectorSpec):
            raise QueryError("select requires SelectorSpec")
        candidates = self._component_candidates(spec)
        tag_candidates = self._tag_candidates(spec)
        if tag_candidates is not None:
            candidates &= tag_candidates
        partition_candidates = self._partition_candidates(spec)
        if partition_candidates is not None:
            candidates &= partition_candidates
        ordered = tuple(sorted(candidates))
        total = len(ordered)
        window = ordered[spec.offset : spec.offset + spec.limit]
        return SelectionResult(
            entity_ids=window,
            total_before_window=total,
            selector_fingerprint=spec.fingerprint,
            store_digest=self.store.state_digest,
            result_digest=digest(
                {
                    "domain": "skeleton.simulation.ecs.selection_result.v1",
                    "selector": spec.fingerprint,
                    "store": self.store.state_digest,
                    "entity_ids": window,
                    "total_before_window": total,
                }
            ),
        )

    def count(self, spec: SelectorSpec) -> int:
        return self.select(spec).total_before_window

    def ids(self, spec: SelectorSpec) -> tuple[str, ...]:
        return self.select(spec).entity_ids

    def contains(self, spec: SelectorSpec, entity_id: str) -> bool:
        if not isinstance(entity_id, str) or not entity_id:
            raise QueryError("entity id must be non-empty text")
        return entity_id in set(self.select(spec).entity_ids)


def union_results(results: Iterable[SelectionResult]) -> tuple[str, ...]:
    found: set[str] = set()
    for result in results:
        if not isinstance(result, SelectionResult):
            raise QueryError("union_results requires SelectionResult values")
        found.update(result.entity_ids)
    return tuple(sorted(found))


def intersect_results(results: Iterable[SelectionResult]) -> tuple[str, ...]:
    rows = tuple(results)
    if not rows:
        return ()
    for result in rows:
        if not isinstance(result, SelectionResult):
            raise QueryError("intersect_results requires SelectionResult values")
    current = set(rows[0].entity_ids)
    for result in rows[1:]:
        current &= set(result.entity_ids)
    return tuple(sorted(current))
