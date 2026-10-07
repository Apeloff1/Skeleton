"""Read-only deterministic component indexes.

The core store deliberately favors simple authoritative dictionaries.
``ComponentIndex`` is a derived acceleration structure that can be rebuilt from
a store at any time and is never serialized as authoritative state.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from .canonical import digest
from .errors import QueryError, ValidationError
from .store import EntityStore


@dataclass(frozen=True)
class IndexSnapshot:
    store_revision: int
    store_digest: str
    by_component: Mapping[str, tuple[str, ...]]
    entity_components: Mapping[str, tuple[str, ...]]
    index_digest: str

    def to_record(self) -> dict[str, Any]:
        return {
            "store_revision": self.store_revision,
            "store_digest": self.store_digest,
            "by_component": {
                key: list(self.by_component[key]) for key in sorted(self.by_component)
            },
            "entity_components": {
                key: list(self.entity_components[key])
                for key in sorted(self.entity_components)
            },
            "index_digest": self.index_digest,
        }


class ComponentIndex:
    """Derived component presence index with stale-state detection."""

    def __init__(self, store: EntityStore) -> None:
        if not isinstance(store, EntityStore):
            raise ValidationError("ComponentIndex requires EntityStore")
        self._snapshot = self._build(store)

    @staticmethod
    def _build(store: EntityStore) -> IndexSnapshot:
        by_component: dict[str, list[str]] = {}
        entity_components: dict[str, tuple[str, ...]] = {}
        for entity_id in store.entity_ids():
            component_ids = store.component_ids(entity_id)
            entity_components[entity_id] = component_ids
            for schema_id in component_ids:
                by_component.setdefault(schema_id, []).append(entity_id)
        frozen_by_component = {
            schema_id: tuple(sorted(entity_ids))
            for schema_id, entity_ids in by_component.items()
        }
        material = {
            "domain": "skeleton.simulation.ecs.component_index.v1",
            "store_revision": store.revision,
            "store_digest": store.state_digest,
            "by_component": frozen_by_component,
            "entity_components": entity_components,
        }
        return IndexSnapshot(
            store_revision=store.revision,
            store_digest=store.state_digest,
            by_component=frozen_by_component,
            entity_components=entity_components,
            index_digest=digest(material),
        )

    @property
    def snapshot(self) -> IndexSnapshot:
        return self._snapshot

    @property
    def store_revision(self) -> int:
        return self._snapshot.store_revision

    @property
    def store_digest(self) -> str:
        return self._snapshot.store_digest

    @property
    def index_digest(self) -> str:
        return self._snapshot.index_digest

    def refresh(self, store: EntityStore) -> IndexSnapshot:
        if not isinstance(store, EntityStore):
            raise ValidationError("refresh requires EntityStore")
        self._snapshot = self._build(store)
        return self._snapshot

    def is_current(self, store: EntityStore) -> bool:
        return (
            isinstance(store, EntityStore)
            and store.revision == self.store_revision
            and store.state_digest == self.store_digest
        )

    def require_current(self, store: EntityStore) -> None:
        if not self.is_current(store):
            raise QueryError(
                "component index is stale",
                context={
                    "index_revision": self.store_revision,
                    "store_revision": getattr(store, "revision", None),
                },
            )

    def schemas(self) -> tuple[str, ...]:
        return tuple(sorted(self._snapshot.by_component))

    def entities_with(self, schema_id: str) -> tuple[str, ...]:
        if not isinstance(schema_id, str) or not schema_id:
            raise QueryError("schema id must be non-empty text")
        return self._snapshot.by_component.get(schema_id, ())

    def components_for(self, entity_id: str) -> tuple[str, ...]:
        if not isinstance(entity_id, str) or not entity_id:
            raise QueryError("entity id must be non-empty text")
        return self._snapshot.entity_components.get(entity_id, ())

    def candidates_all(self, schema_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        schema_ids = tuple(sorted(set(schema_ids)))
        if not schema_ids:
            return tuple(sorted(self._snapshot.entity_components))
        candidate_sets = [
            set(self.entities_with(schema_id))
            for schema_id in schema_ids
        ]
        if not candidate_sets:
            return ()
        result = set.intersection(*candidate_sets)
        return tuple(sorted(result))

    def candidates_any(self, schema_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        schema_ids = tuple(sorted(set(schema_ids)))
        result: set[str] = set()
        for schema_id in schema_ids:
            result.update(self.entities_with(schema_id))
        return tuple(sorted(result))

    def candidates_none(self, schema_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        excluded = set(self.candidates_any(schema_ids))
        return tuple(
            entity_id
            for entity_id in sorted(self._snapshot.entity_components)
            if entity_id not in excluded
        )
