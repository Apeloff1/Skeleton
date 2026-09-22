"""Deterministic entity tags and directed relation graph."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .canonical import digest
from .errors import BoundsError, EntityNotFoundError, ValidationError
from .store import EntityStore

MAX_TAGS_PER_ENTITY = 256
MAX_RELATIONS = 1_000_000
_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


def _token(name: str, value: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValidationError(f"invalid {name}", context={name: value})
    return value


@dataclass(frozen=True, order=True)
class RelationKey:
    relation_type: str
    source: str
    target: str

    def __post_init__(self) -> None:
        _token("relation_type", self.relation_type)
        if not isinstance(self.source, str) or not self.source:
            raise ValidationError("relation source must be non-empty text")
        if not isinstance(self.target, str) or not self.target:
            raise ValidationError("relation target must be non-empty text")


@dataclass(frozen=True)
class Relation:
    key: RelationKey
    metadata: Mapping[str, Any]
    created_revision: int
    updated_revision: int

    def to_record(self) -> dict[str, Any]:
        return {
            "relation_type": self.key.relation_type,
            "source": self.key.source,
            "target": self.key.target,
            "metadata": copy.deepcopy(dict(self.metadata)),
            "created_revision": self.created_revision,
            "updated_revision": self.updated_revision,
        }


@dataclass(frozen=True)
class RelationSnapshot:
    revision: int
    tags: Mapping[str, tuple[str, ...]]
    relations: tuple[Relation, ...]
    graph_digest: str


class RelationGraph:
    def __init__(self, store: EntityStore) -> None:
        if not isinstance(store, EntityStore):
            raise ValidationError("RelationGraph requires EntityStore")
        self.store = store
        self._tags: dict[str, set[str]] = {}
        self._relations: dict[RelationKey, Relation] = {}
        self._revision = 0

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def relation_count(self) -> int:
        return len(self._relations)

    def _bump(self) -> int:
        self._revision += 1
        return self._revision

    def _require_entity(self, entity_id: str) -> None:
        if not self.store.has_entity(entity_id):
            raise EntityNotFoundError(
                "relation endpoint entity not found",
                context={"entity_id": entity_id},
            )

    def add_tag(self, entity_id: str, tag: str) -> bool:
        self._require_entity(entity_id)
        tag = _token("tag", tag)
        tags = self._tags.setdefault(entity_id, set())
        if tag in tags:
            return False
        if len(tags) >= MAX_TAGS_PER_ENTITY:
            raise BoundsError(
                "entity tag bound exceeded",
                context={"entity_id": entity_id, "maximum": MAX_TAGS_PER_ENTITY},
            )
        tags.add(tag)
        self._bump()
        return True

    def remove_tag(self, entity_id: str, tag: str) -> bool:
        self._require_entity(entity_id)
        tag = _token("tag", tag)
        tags = self._tags.get(entity_id)
        if not tags or tag not in tags:
            return False
        tags.remove(tag)
        if not tags:
            self._tags.pop(entity_id, None)
        self._bump()
        return True

    def tags(self, entity_id: str) -> tuple[str, ...]:
        self._require_entity(entity_id)
        return tuple(sorted(self._tags.get(entity_id, ())))

    def entities_with_tag(self, tag: str) -> tuple[str, ...]:
        tag = _token("tag", tag)
        return tuple(
            sorted(entity_id for entity_id, tags in self._tags.items() if tag in tags)
        )

    def set_relation(
        self,
        relation_type: str,
        source: str,
        target: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> Relation:
        self._require_entity(source)
        self._require_entity(target)
        key = RelationKey(_token("relation_type", relation_type), source, target)
        frozen = copy.deepcopy(dict(metadata or {}))
        digest(frozen)
        existing = self._relations.get(key)
        if existing is None and len(self._relations) >= MAX_RELATIONS:
            raise BoundsError("relation bound exceeded", context={"maximum": MAX_RELATIONS})
        revision = self._bump()
        relation = Relation(
            key=key,
            metadata=frozen,
            created_revision=existing.created_revision if existing else revision,
            updated_revision=revision,
        )
        self._relations[key] = relation
        return relation

    def remove_relation(self, relation_type: str, source: str, target: str) -> bool:
        key = RelationKey(_token("relation_type", relation_type), source, target)
        if key not in self._relations:
            return False
        del self._relations[key]
        self._bump()
        return True

    def get_relation(self, relation_type: str, source: str, target: str) -> Relation | None:
        key = RelationKey(_token("relation_type", relation_type), source, target)
        return self._relations.get(key)

    def outgoing(self, source: str, relation_type: str | None = None) -> tuple[Relation, ...]:
        self._require_entity(source)
        if relation_type is not None:
            relation_type = _token("relation_type", relation_type)
        rows = [
            relation
            for relation in self._relations.values()
            if relation.key.source == source
            and (relation_type is None or relation.key.relation_type == relation_type)
        ]
        return tuple(sorted(rows, key=lambda row: row.key))

    def incoming(self, target: str, relation_type: str | None = None) -> tuple[Relation, ...]:
        self._require_entity(target)
        if relation_type is not None:
            relation_type = _token("relation_type", relation_type)
        rows = [
            relation
            for relation in self._relations.values()
            if relation.key.target == target
            and (relation_type is None or relation.key.relation_type == relation_type)
        ]
        return tuple(sorted(rows, key=lambda row: row.key))

    def neighbors(
        self,
        entity_id: str,
        *,
        relation_type: str | None = None,
        direction: str = "both",
    ) -> tuple[str, ...]:
        self._require_entity(entity_id)
        if direction not in {"in", "out", "both"}:
            raise ValidationError("relation direction must be in/out/both")
        found: set[str] = set()
        if direction in {"out", "both"}:
            found.update(row.key.target for row in self.outgoing(entity_id, relation_type))
        if direction in {"in", "both"}:
            found.update(row.key.source for row in self.incoming(entity_id, relation_type))
        return tuple(sorted(found))

    def relation_types(self) -> tuple[str, ...]:
        return tuple(sorted({key.relation_type for key in self._relations}))

    def roots(self, relation_type: str) -> tuple[str, ...]:
        relation_type = _token("relation_type", relation_type)
        nodes = set(self.store.entity_ids())
        targets = {
            key.target for key in self._relations if key.relation_type == relation_type
        }
        return tuple(sorted(nodes - targets))

    def descendants(
        self,
        entity_id: str,
        relation_type: str,
        *,
        max_depth: int = 256,
    ) -> tuple[str, ...]:
        self._require_entity(entity_id)
        relation_type = _token("relation_type", relation_type)
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
            raise ValidationError("max_depth must be non-negative integer")
        seen: set[str] = set()
        frontier = [entity_id]
        depth = 0
        while frontier:
            if depth >= max_depth:
                if any(self.outgoing(node, relation_type) for node in frontier):
                    raise BoundsError(
                        "relation traversal depth exceeded",
                        context={"maximum": max_depth},
                    )
                break
            next_frontier: list[str] = []
            for current in sorted(frontier):
                for relation in self.outgoing(current, relation_type):
                    target = relation.key.target
                    if target == entity_id:
                        raise ValidationError(
                            "relation traversal detected cycle",
                            context={"entity_id": entity_id, "relation_type": relation_type},
                        )
                    if target not in seen:
                        seen.add(target)
                        next_frontier.append(target)
            frontier = next_frontier
            depth += 1
        return tuple(sorted(seen))

    def purge_missing_entities(self) -> tuple[RelationKey, ...]:
        live = set(self.store.entity_ids())
        removed: list[RelationKey] = []
        for key in sorted(self._relations):
            if key.source not in live or key.target not in live:
                removed.append(key)
        for key in removed:
            del self._relations[key]
        for entity_id in tuple(self._tags):
            if entity_id not in live:
                del self._tags[entity_id]
        if removed:
            self._bump()
        return tuple(removed)

    def snapshot(self) -> RelationSnapshot:
        tags = {
            entity_id: tuple(sorted(values))
            for entity_id, values in sorted(self._tags.items())
        }
        relations = tuple(self._relations[key] for key in sorted(self._relations))
        material = {
            "domain": "skeleton.simulation.ecs.relation_graph.v1",
            "revision": self._revision,
            "tags": tags,
            "relations": [row.to_record() for row in relations],
        }
        return RelationSnapshot(
            revision=self._revision,
            tags=tags,
            relations=relations,
            graph_digest=digest(material),
        )

    @property
    def graph_digest(self) -> str:
        return self.snapshot().graph_digest
