"""Derived sparse component tables for deterministic bulk iteration."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from .canonical import digest
from .errors import QueryError, ValidationError
from .store import ComponentValue, EntityStore


@dataclass(frozen=True)
class TableRow:
    entity_id: str
    component: ComponentValue


@dataclass(frozen=True)
class TableSnapshot:
    schema_id: str
    store_revision: int
    store_digest: str
    entity_ids: tuple[str, ...]
    table_digest: str


class ComponentTable:
    def __init__(self, store: EntityStore, schema_id: str) -> None:
        if not isinstance(store, EntityStore):
            raise ValidationError("ComponentTable requires EntityStore")
        if not isinstance(schema_id, str) or not schema_id:
            raise ValidationError("component table schema id required")
        self.schema_id = schema_id
        self._store_revision = -1
        self._store_digest = ""
        self._entity_ids: tuple[str, ...] = ()
        self.refresh(store)

    def refresh(self, store: EntityStore) -> TableSnapshot:
        entity_ids = tuple(
            entity_id
            for entity_id in store.entity_ids()
            if store.has_component(entity_id, self.schema_id)
        )
        self._store_revision = store.revision
        self._store_digest = store.state_digest
        self._entity_ids = entity_ids
        return self.snapshot()

    def is_current(self, store: EntityStore) -> bool:
        return (
            isinstance(store, EntityStore)
            and store.revision == self._store_revision
            and store.state_digest == self._store_digest
        )

    def require_current(self, store: EntityStore) -> None:
        if not self.is_current(store):
            raise QueryError(
                "component table is stale",
                context={
                    "schema_id": self.schema_id,
                    "table_revision": self._store_revision,
                    "store_revision": getattr(store, "revision", None),
                },
            )

    def entity_ids(self, store: EntityStore) -> tuple[str, ...]:
        self.require_current(store)
        return self._entity_ids

    def rows(self, store: EntityStore) -> tuple[TableRow, ...]:
        self.require_current(store)
        return tuple(
            TableRow(entity_id, store.get_component(entity_id, self.schema_id))
            for entity_id in self._entity_ids
        )

    def values(self, store: EntityStore) -> tuple[Mapping[str, Any], ...]:
        return tuple(copy.deepcopy(dict(row.component.data)) for row in self.rows(store))

    def field(self, store: EntityStore, field_name: str) -> tuple[tuple[str, Any], ...]:
        if not isinstance(field_name, str) or not field_name:
            raise QueryError("field name must be non-empty text")
        rows: list[tuple[str, Any]] = []
        for row in self.rows(store):
            if field_name not in row.component.data:
                raise QueryError(
                    "component field missing",
                    context={
                        "schema_id": self.schema_id,
                        "entity_id": row.entity_id,
                        "field": field_name,
                    },
                )
            rows.append((row.entity_id, copy.deepcopy(row.component.data[field_name])))
        return tuple(rows)

    def snapshot(self) -> TableSnapshot:
        material = {
            "domain": "skeleton.simulation.ecs.component_table.v1",
            "schema_id": self.schema_id,
            "store_revision": self._store_revision,
            "store_digest": self._store_digest,
            "entity_ids": self._entity_ids,
        }
        return TableSnapshot(
            schema_id=self.schema_id,
            store_revision=self._store_revision,
            store_digest=self._store_digest,
            entity_ids=self._entity_ids,
            table_digest=digest(material),
        )


class TableRegistry:
    def __init__(self, store: EntityStore) -> None:
        self.store = store
        self._tables: dict[str, ComponentTable] = {}

    def get(self, schema_id: str) -> ComponentTable:
        table = self._tables.get(schema_id)
        if table is None:
            table = ComponentTable(self.store, schema_id)
            self._tables[schema_id] = table
        elif not table.is_current(self.store):
            table.refresh(self.store)
        return table

    def refresh_all(self) -> tuple[TableSnapshot, ...]:
        return tuple(
            self._tables[schema_id].refresh(self.store)
            for schema_id in sorted(self._tables)
        )

    def known_schema_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._tables))

    @property
    def fingerprint(self) -> str:
        snapshots = [
            self._tables[schema_id].snapshot().__dict__
            for schema_id in sorted(self._tables)
        ]
        return digest(
            {
                "domain": "skeleton.simulation.ecs.table_registry.v1",
                "store_digest": self.store.state_digest,
                "tables": snapshots,
            }
        )
