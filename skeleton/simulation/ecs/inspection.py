"""Deterministic state inspection and structural diff utilities."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .canonical import digest
from .execution import StoreSnapshot, capture_snapshot
from .store import EntityStore


class ChangeKind(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class ComponentChange:
    entity_id: str
    schema_id: str
    kind: ChangeKind
    before: Any
    after: Any


@dataclass(frozen=True)
class EntityChange:
    entity_id: str
    kind: ChangeKind
    component_changes: tuple[ComponentChange, ...]


@dataclass(frozen=True)
class ResourceChange:
    resource_id: str
    kind: ChangeKind
    before: Any
    after: Any


@dataclass(frozen=True)
class StateDiff:
    before_digest: str
    after_digest: str
    entities: tuple[EntityChange, ...]
    resources: tuple[ResourceChange, ...]
    diff_digest: str

    @property
    def changed(self) -> bool:
        return self.before_digest != self.after_digest

    @property
    def changed_entities(self) -> tuple[str, ...]:
        return tuple(
            row.entity_id for row in self.entities if row.kind is not ChangeKind.UNCHANGED
        )


@dataclass(frozen=True)
class EntityInspection:
    entity_id: str
    components: Mapping[str, Mapping[str, Any]]
    entity_digest: str


@dataclass(frozen=True)
class StoreInspection:
    revision: int
    tick: int
    entity_ids: tuple[str, ...]
    resource_ids: tuple[str, ...]
    tombstone_ids: tuple[str, ...]
    schema_ids: tuple[str, ...]
    state_digest: str
    inspection_digest: str


def inspect_entity(store: EntityStore, entity_id: str) -> EntityInspection:
    record = store.get_entity(entity_id)
    components = {
        schema_id: copy.deepcopy(dict(record.components[schema_id].data))
        for schema_id in sorted(record.components)
    }
    return EntityInspection(
        entity_id=entity_id,
        components=components,
        entity_digest=digest(
            {
                "entity_id": entity_id,
                "components": components,
                "created_revision": record.created_revision,
                "updated_revision": record.updated_revision,
            }
        ),
    )


def inspect_store(store: EntityStore) -> StoreInspection:
    schema_ids = tuple(sorted({row["schema_id"] for row in store.registry.catalog()}))
    material = {
        "revision": store.revision,
        "tick": store.tick,
        "entity_ids": store.entity_ids(),
        "resource_ids": store.resource_ids(),
        "tombstone_ids": store.tombstone_ids(),
        "schema_ids": schema_ids,
        "state_digest": store.state_digest,
    }
    return StoreInspection(
        revision=store.revision,
        tick=store.tick,
        entity_ids=store.entity_ids(),
        resource_ids=store.resource_ids(),
        tombstone_ids=store.tombstone_ids(),
        schema_ids=schema_ids,
        state_digest=store.state_digest,
        inspection_digest=digest(material),
    )


def _entity_components(snapshot: StoreSnapshot) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entity_id in snapshot.store.entity_ids():
        record = snapshot.store.get_entity(entity_id)
        result[entity_id] = {
            schema_id: copy.deepcopy(dict(record.components[schema_id].data))
            for schema_id in sorted(record.components)
        }
    return result


def diff_state(
    before: EntityStore | StoreSnapshot,
    after: EntityStore | StoreSnapshot,
    *,
    include_unchanged: bool = False,
) -> StateDiff:
    before_snapshot = before if isinstance(before, StoreSnapshot) else capture_snapshot(before)
    after_snapshot = after if isinstance(after, StoreSnapshot) else capture_snapshot(after)
    before_entities = _entity_components(before_snapshot)
    after_entities = _entity_components(after_snapshot)
    entity_rows: list[EntityChange] = []
    for entity_id in sorted(set(before_entities) | set(after_entities)):
        left = before_entities.get(entity_id)
        right = after_entities.get(entity_id)
        if left is None:
            kind = ChangeKind.ADDED
        elif right is None:
            kind = ChangeKind.REMOVED
        elif left == right:
            kind = ChangeKind.UNCHANGED
        else:
            kind = ChangeKind.CHANGED
        component_rows: list[ComponentChange] = []
        left_components = left or {}
        right_components = right or {}
        for schema_id in sorted(set(left_components) | set(right_components)):
            left_value = left_components.get(schema_id)
            right_value = right_components.get(schema_id)
            if schema_id not in left_components:
                component_kind = ChangeKind.ADDED
            elif schema_id not in right_components:
                component_kind = ChangeKind.REMOVED
            elif left_value == right_value:
                component_kind = ChangeKind.UNCHANGED
            else:
                component_kind = ChangeKind.CHANGED
            if include_unchanged or component_kind is not ChangeKind.UNCHANGED:
                component_rows.append(
                    ComponentChange(
                        entity_id,
                        schema_id,
                        component_kind,
                        copy.deepcopy(left_value),
                        copy.deepcopy(right_value),
                    )
                )
        if include_unchanged or kind is not ChangeKind.UNCHANGED:
            entity_rows.append(EntityChange(entity_id, kind, tuple(component_rows)))

    resource_rows: list[ResourceChange] = []
    before_resources = {
        rid: copy.deepcopy(before_snapshot.store.get_resource(rid).value)
        for rid in before_snapshot.store.resource_ids()
    }
    after_resources = {
        rid: copy.deepcopy(after_snapshot.store.get_resource(rid).value)
        for rid in after_snapshot.store.resource_ids()
    }
    for resource_id in sorted(set(before_resources) | set(after_resources)):
        if resource_id not in before_resources:
            kind = ChangeKind.ADDED
        elif resource_id not in after_resources:
            kind = ChangeKind.REMOVED
        elif before_resources[resource_id] == after_resources[resource_id]:
            kind = ChangeKind.UNCHANGED
        else:
            kind = ChangeKind.CHANGED
        if include_unchanged or kind is not ChangeKind.UNCHANGED:
            resource_rows.append(
                ResourceChange(
                    resource_id,
                    kind,
                    copy.deepcopy(before_resources.get(resource_id)),
                    copy.deepcopy(after_resources.get(resource_id)),
                )
            )

    material = {
        "domain": "skeleton.simulation.ecs.state_diff.v1",
        "before_digest": before_snapshot.state_digest,
        "after_digest": after_snapshot.state_digest,
        "entities": [
            {
                "entity_id": row.entity_id,
                "kind": row.kind.value,
                "components": [
                    {
                        "schema_id": component.schema_id,
                        "kind": component.kind.value,
                        "before": component.before,
                        "after": component.after,
                    }
                    for component in row.component_changes
                ],
            }
            for row in entity_rows
        ],
        "resources": [
            {
                "resource_id": row.resource_id,
                "kind": row.kind.value,
                "before": row.before,
                "after": row.after,
            }
            for row in resource_rows
        ],
    }
    return StateDiff(
        before_digest=before_snapshot.state_digest,
        after_digest=after_snapshot.state_digest,
        entities=tuple(entity_rows),
        resources=tuple(resource_rows),
        diff_digest=digest(material),
    )
