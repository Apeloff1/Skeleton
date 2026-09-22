"""Authoritative deterministic entity/component/resource store."""
from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

from .canonical import digest
from .errors import (BoundsError, ComponentExistsError, ComponentNotFoundError,
                     EntityExistsError, EntityNotFoundError, EntityTombstonedError,
                     ResourceNotFoundError, TransactionError, ValidationError)
from .identity import EntityAllocator, EntityId, validate_entity_id
from .schema import SchemaRegistry

MAX_ENTITIES = 1_000_000
MAX_COMPONENTS_PER_ENTITY = 256
MAX_RESOURCES = 4096
MAX_TOMBSTONES = 1_000_000


@dataclass(frozen=True)
class ComponentValue:
    schema_id: str
    schema_version: int
    data: Mapping[str, Any]

    def to_record(self) -> dict[str, Any]:
        return {"schema_id": self.schema_id, "schema_version": self.schema_version, "data": copy.deepcopy(dict(self.data))}


@dataclass(frozen=True)
class ResourceValue:
    resource_id: str
    value: Any

    def to_record(self) -> dict[str, Any]:
        return {"resource_id": self.resource_id, "value": copy.deepcopy(self.value)}


@dataclass(frozen=True)
class EntityRecord:
    entity_id: str
    components: Mapping[str, ComponentValue]
    created_revision: int
    updated_revision: int

    def to_record(self) -> dict[str, Any]:
        return {"entity_id": self.entity_id, "components": {key: self.components[key].to_record() for key in sorted(self.components)}, "created_revision": self.created_revision, "updated_revision": self.updated_revision}


@dataclass(frozen=True)
class Tombstone:
    entity_id: str
    deleted_revision: int
    prior_digest: str
    def to_record(self) -> dict[str, Any]: return {"entity_id": self.entity_id, "deleted_revision": self.deleted_revision, "prior_digest": self.prior_digest}


class EntityStore:
    def __init__(self, registry: SchemaRegistry | None = None, *, allocator: EntityAllocator | None = None) -> None:
        self.registry = registry or SchemaRegistry(); self.allocator = allocator or EntityAllocator(); self._entities = {}; self._resources = {}; self._tombstones = {}; self.revision = 0; self.tick = 0
    def _bump(self) -> int: self.revision += 1; return self.revision
    @property
    def entity_count(self) -> int: return len(self._entities)
    @property
    def component_count(self) -> int: return sum(len(e.components) for e in self._entities.values())
    @property
    def resource_count(self) -> int: return len(self._resources)
    @property
    def tombstone_count(self) -> int: return len(self._tombstones)
    @property
    def state_digest(self) -> str: return digest(self.to_record())
    def entity_ids(self) -> tuple[str, ...]: return tuple(sorted(self._entities))
    def resource_ids(self) -> tuple[str, ...]: return tuple(sorted(self._resources))
    def tombstone_ids(self) -> tuple[str, ...]: return tuple(sorted(self._tombstones))
    def has_entity(self, entity_id: str) -> bool: return entity_id in self._entities
    def is_tombstoned(self, entity_id: str) -> bool: return entity_id in self._tombstones
    def create_entity(self, entity_id: str | EntityId | None = None, *, hint: str | None = None) -> EntityRecord:
        if self.entity_count >= MAX_ENTITIES: raise BoundsError("entity bound exceeded", context={"maximum": MAX_ENTITIES})
        if entity_id is None: eid = self.allocator.allocate(hint).value
        elif isinstance(entity_id, EntityId): eid = entity_id.value
        else: eid = validate_entity_id(entity_id)
        if eid in self._entities: raise EntityExistsError("entity already exists", context={"entity_id": eid})
        if eid in self._tombstones: raise EntityTombstonedError("entity id is tombstoned", context={"entity_id": eid})
        rev = self._bump(); record = EntityRecord(eid, {}, rev, rev); self._entities[eid] = record; return record
    def get_entity(self, entity_id: str) -> EntityRecord:
        if entity_id not in self._entities: raise EntityNotFoundError("entity not found", context={"entity_id": entity_id})
        return self._entities[entity_id]
    def delete_entity(self, entity_id: str) -> Tombstone:
        record = self.get_entity(entity_id)
        if self.tombstone_count >= MAX_TOMBSTONES: raise BoundsError("tombstone bound exceeded")
        prior = digest(record.to_record()); rev = self._bump(); tombstone = Tombstone(entity_id, rev, prior); del self._entities[entity_id]; self._tombstones[entity_id] = tombstone; return tombstone
    def component_ids(self, entity_id: str) -> tuple[str, ...]: return tuple(sorted(self.get_entity(entity_id).components))
    def has_component(self, entity_id: str, schema_id: str) -> bool: return schema_id in self.get_entity(entity_id).components
    def get_component(self, entity_id: str, schema_id: str) -> ComponentValue:
        record = self.get_entity(entity_id)
        if schema_id not in record.components: raise ComponentNotFoundError("component not found", context={"entity_id": entity_id, "schema_id": schema_id})
        return record.components[schema_id]
    def set_component(self, entity_id: str, schema_id: str, data: Mapping[str, Any], *, version: int | None = None, replace: bool = True) -> ComponentValue:
        record = self.get_entity(entity_id); schema = self.registry.get(schema_id, version)
        if schema_id in record.components and not replace: raise ComponentExistsError("component already exists", context={"entity_id": entity_id, "schema_id": schema_id})
        if schema_id not in record.components and len(record.components) >= MAX_COMPONENTS_PER_ENTITY: raise BoundsError("component-per-entity bound exceeded")
        value = ComponentValue(schema.schema_id, schema.version, schema.validate(data)); rev = self._bump(); components = dict(record.components); components[schema_id] = value; self._entities[entity_id] = EntityRecord(entity_id, components, record.created_revision, rev); return value
    def patch_component(self, entity_id: str, schema_id: str, patch: Mapping[str, Any]) -> ComponentValue:
        current = self.get_component(entity_id, schema_id); merged = dict(current.data); merged.update(copy.deepcopy(dict(patch))); return self.set_component(entity_id, schema_id, merged, version=current.schema_version)
    def remove_component(self, entity_id: str, schema_id: str) -> ComponentValue:
        record = self.get_entity(entity_id); current = self.get_component(entity_id, schema_id); components = dict(record.components); del components[schema_id]; rev = self._bump(); self._entities[entity_id] = EntityRecord(entity_id, components, record.created_revision, rev); return current
    def set_resource(self, resource_id: str, value: Any) -> ResourceValue:
        if not isinstance(resource_id, str) or not resource_id: raise ValidationError("resource id must be non-empty text")
        if resource_id not in self._resources and len(self._resources) >= MAX_RESOURCES: raise BoundsError("resource bound exceeded")
        digest(value); rv = ResourceValue(resource_id, copy.deepcopy(value)); self._resources[resource_id] = rv; self._bump(); return rv
    def get_resource(self, resource_id: str) -> ResourceValue:
        if resource_id not in self._resources: raise ResourceNotFoundError("resource not found", context={"resource_id": resource_id})
        return self._resources[resource_id]
    def remove_resource(self, resource_id: str) -> ResourceValue: current = self.get_resource(resource_id); del self._resources[resource_id]; self._bump(); return current
    def advance_tick(self, tick: int) -> None:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < self.tick: raise ValidationError("tick must be monotonic integer")
        if tick != self.tick: self.tick = tick; self._bump()
    def to_record(self) -> dict[str, Any]:
        return {"schema": "simulation.entity_store.v1", "revision": self.revision, "tick": self.tick, "allocator": self.allocator.snapshot(), "schemas": self.registry.catalog(), "entities": [self._entities[eid].to_record() for eid in sorted(self._entities)], "resources": [self._resources[rid].to_record() for rid in sorted(self._resources)], "tombstones": [self._tombstones[eid].to_record() for eid in sorted(self._tombstones)]}
    def clone(self) -> "EntityStore": return copy.deepcopy(self)
    def replace_from(self, other: "EntityStore") -> None:
        if not isinstance(other, EntityStore): raise ValidationError("replace_from requires EntityStore")
        self.registry = copy.deepcopy(other.registry); self.allocator = copy.deepcopy(other.allocator); self._entities = copy.deepcopy(other._entities); self._resources = copy.deepcopy(other._resources); self._tombstones = copy.deepcopy(other._tombstones); self.revision = other.revision; self.tick = other.tick
    @contextmanager
    def transaction(self) -> Iterator["EntityStore"]:
        snapshot = self.clone()
        try: yield self
        except Exception: self.replace_from(snapshot); raise
    def assert_invariants(self) -> None:
        if set(self._entities) & set(self._tombstones): raise TransactionError("live entity also tombstoned")
        for entity_id, record in self._entities.items():
            if entity_id != record.entity_id: raise TransactionError("entity key mismatch")
            if len(record.components) > MAX_COMPONENTS_PER_ENTITY: raise TransactionError("component bound violated")
            for schema_id, component in record.components.items():
                if schema_id != component.schema_id: raise TransactionError("component key mismatch")
                self.registry.get(component.schema_id, component.schema_version).validate(component.data)
