"""Serialisation, snapshots, rollback and ``EntityStore`` bridging for live worlds.

Two identities are defined over a :class:`~.live.LiveWorld`:

``state_record`` / ``state_digest``
    *Game state*: tick, entities (ascending slot order) with their component
    values, resources, pending events, RNG state and allocator state.  It is
    layout independent — two worlds that reached the same state through a
    different sequence of archetype moves hash identically.

``WorldSnapshot``
    *Exact runtime state*: everything above **plus** physical layout (table
    creation order, row order, sparse-set order), change ticks and trackers.
    Restoring a snapshot reproduces not only the state but also iteration
    order, so a restored world continues bit-identically — the property
    deterministic rollback/netcode and replay verification need.

Snapshots serialise to canonical JSON through the existing
:func:`~.codec.encode_document` envelope (digest-bound, tamper evident).
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .canonical import digest
from .channels import EventBus
from .codec import decode_document, encode_document
from .components import ComponentRegistry, StorageKind
from .entities import RESERVED, HandleAllocator, handle_from_text, handle_to_text
from .errors import (
    ECSError,
    SnapshotDigestError,
    SnapshotError,
    SnapshotVersionError,
    ValidationError,
)
from .rng import DeterministicRng
from .storage import ArchetypeGraph, SparseSet
from .values import copy_value, from_json, to_json

SNAPSHOT_SCHEMA = "simulation.ecs.live_world_snapshot.v1"
STATE_SCHEMA = "simulation.ecs.live_world_state.v1"
MAX_RING = 4096


def _require_quiescent(world) -> None:
    if world._iterating:
        raise SnapshotError("cannot snapshot while a query iterator is active")
    if RESERVED in world.entities._states:
        raise SnapshotError("cannot snapshot with unapplied command-queue reservations")


def state_record(world) -> dict[str, Any]:
    registry = world.components
    entities = []
    for handle in world.iter_entities():
        comps = {}
        for name in world.components_of(handle):
            comps[name] = to_json(world.get(handle, name))
        entities.append([handle_to_text(handle), comps])
    return {
        "schema": STATE_SCHEMA,
        "name": world.name,
        "tick": world.tick,
        "components": registry.fingerprint,
        "entities": entities,
        "resources": {k: to_json(world.resources[k]) for k in sorted(world.resources)},
        "events": world.events.to_record(),
        "rng": world.rng.state(),
        "allocator": world.entities.snapshot(),
        "meta": {k: to_json(world.meta[k]) for k in sorted(world.meta)},
    }


@dataclass(frozen=True)
class WorldSnapshot:
    payload: Mapping[str, Any]
    snapshot_digest: str
    state_digest: str
    tick: int

    def verify(self) -> None:
        if digest(dict(self.payload)) != self.snapshot_digest:
            raise SnapshotDigestError("live world snapshot digest mismatch")


def _layout_payload(world) -> dict[str, Any]:
    registry = world.components
    tables = []
    for table in world.graph.tables:
        names = [registry.by_id(cid).name for cid in table.signature]
        tables.append({
            "signature": names,
            "entities": list(table.entities),
            "columns": {registry.by_id(cid).name: [to_json(v) for v in table.columns[cid]] for cid in table.signature},
            "added": {registry.by_id(cid).name: list(table.added[cid]) for cid in table.signature},
            "changed": {registry.by_id(cid).name: list(table.changed[cid]) for cid in table.signature},
        })
    sparse = {}
    for cid in sorted(world.sparse):
        s = world.sparse[cid]
        sparse[registry.by_id(cid).name] = {
            "entities": list(s.entities),
            "values": [to_json(v) for v in s.values],
            "added": list(s.added),
            "changed": list(s.changed),
        }
    removed = {registry.by_id(cid).name: list(hs) for cid, hs in sorted(world._removed.items())}
    removed_previous = {registry.by_id(cid).name: list(hs) for cid, hs in sorted(world._removed_previous.items())}
    return {"tables": tables, "sparse": sparse, "removed": removed, "removed_previous": removed_previous}


def capture(world) -> WorldSnapshot:
    _require_quiescent(world)
    payload = {
        "schema": SNAPSHOT_SCHEMA,
        "name": world.name,
        "tick": world.tick,
        "change_tick": world.change_tick,
        "components": world.components.catalog(),
        "allocator": world.entities.snapshot(),
        "layout": _layout_payload(world),
        "resources": {k: to_json(world.resources[k]) for k in sorted(world.resources)},
        "events": world.events.to_record(),
        "rng": world.rng.state(),
        "meta": {k: to_json(world.meta[k]) for k in sorted(world.meta)},
    }
    return WorldSnapshot(payload, digest(payload), world.state_digest, world.tick)


def restore(world, snapshot: WorldSnapshot) -> None:
    """Replace ``world``'s entire state with ``snapshot`` (in place)."""
    if not isinstance(snapshot, WorldSnapshot):
        raise SnapshotError("restore requires a WorldSnapshot")
    if world._iterating:
        raise SnapshotError("cannot restore while a query iterator is active")
    snapshot.verify()
    _restore_payload(world, snapshot.payload)
    if world.state_digest != snapshot.state_digest:
        raise SnapshotDigestError("restored world state digest mismatch")


def _restore_payload(world, payload: Mapping[str, Any]) -> None:
    """Rebuild ``world`` from a snapshot payload (structure fully validated)."""
    if payload.get("schema") != SNAPSHOT_SCHEMA:
        raise SnapshotVersionError("unsupported live world snapshot schema", context={"schema": payload.get("schema")})
    # The snapshot's catalog is authoritative: ids are dense registration
    # order, so any component registered after the snapshot keeps no state.
    registry = ComponentRegistry.from_catalog(payload["components"])
    allocator = HandleAllocator.restore(payload["allocator"])
    graph = ArchetypeGraph()
    loc_table: list[int] = [-1] * allocator.slot_count
    loc_row: list[int] = [-1] * allocator.slot_count
    placed: set[int] = set()
    layout = payload["layout"]
    for position, row in enumerate(layout["tables"]):
        signature = tuple(sorted(registry.id_of(n) for n in row["signature"]))
        if position == 0 and signature:
            raise SnapshotError("first snapshot table must be the empty archetype")
        table = graph.get_or_create(signature)
        if table.table_id != position:
            raise SnapshotError("snapshot tables are not in creation order")
        for r, handle in enumerate(row["entities"]):
            if not allocator.is_alive(handle) or handle in placed:
                raise SnapshotError("snapshot table references a dead or duplicate entity")
            placed.add(handle)
            values = {registry.id_of(n): from_json(row["columns"][n][r]) for n in row["signature"]}
            ticks = {registry.id_of(n): (int(row["added"][n][r]), int(row["changed"][n][r])) for n in row["signature"]}
            table.push(handle, values, ticks)
            index = handle & 0xFFFFFFFF
            loc_table[index] = table.table_id
            loc_row[index] = r
    if placed != set(allocator.alive_handles()):
        raise SnapshotError("snapshot layout does not cover every alive entity")
    # Rebuild archetype edges lazily (they are a cache, not state).
    sparse_sets: dict[int, SparseSet] = {}
    for info in registry.infos():
        if info.storage is StorageKind.SPARSE:
            sparse_sets[info.component_id] = SparseSet(info.component_id)
    for name, row in layout["sparse"].items():
        info = registry.get(name)
        if info.storage is not StorageKind.SPARSE:
            raise SnapshotError("sparse layout for a table component", context={"component": name})
        s = sparse_sets[info.component_id]
        for handle, value, added, changed in zip(row["entities"], row["values"], row["added"], row["changed"]):
            if not allocator.is_alive(handle):
                raise SnapshotError("sparse set references a dead entity", context={"component": name})
            s.restore_row(handle, from_json(value), int(added), int(changed))
    removed = {registry.id_of(name): list(hs) for name, hs in layout.get("removed", {}).items()}
    removed_previous = {registry.id_of(name): list(hs) for name, hs in layout.get("removed_previous", {}).items()}

    world.components = registry
    world.entities = allocator
    world.graph = graph
    world.sparse = sparse_sets
    world._loc_table = loc_table
    world._loc_row = loc_row
    world._removed = removed
    world._removed_previous = removed_previous
    world.meta = {k: from_json(v) for k, v in payload.get("meta", {}).items()}
    world.resources = {k: from_json(v) for k, v in payload["resources"].items()}
    world.events = EventBus.from_record(payload["events"])
    world.rng = DeterministicRng.from_state(payload["rng"])
    world.tick = int(payload["tick"])
    world.change_tick = int(payload["change_tick"])
    world.name = payload["name"]


def world_from_snapshot(snapshot: WorldSnapshot):
    from .live import LiveWorld

    world = LiveWorld(name=snapshot.payload["name"])
    restore(world, snapshot)
    return world


def encode_snapshot(snapshot: WorldSnapshot) -> str:
    snapshot.verify()
    return encode_document(SNAPSHOT_SCHEMA, {
        "payload": dict(snapshot.payload),
        "state_digest": snapshot.state_digest,
        "tick": snapshot.tick,
    })


def decode_snapshot(text: str) -> WorldSnapshot:
    document = decode_document(text, expected_schema=SNAPSHOT_SCHEMA)
    body = document.payload
    if set(body) != {"payload", "state_digest", "tick"}:
        raise SnapshotError("snapshot document fields mismatch")
    payload = body["payload"]
    snapshot = WorldSnapshot(payload, digest(payload), body["state_digest"], int(body["tick"]))
    return snapshot


class SnapshotRing:
    """Bounded tick-indexed snapshot history for rollback (e.g. netcode)."""

    def __init__(self, capacity: int = 128) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or not 1 <= capacity <= MAX_RING:
            raise SnapshotError("invalid snapshot ring capacity")
        self.capacity = capacity
        self._items: deque[WorldSnapshot] = deque(maxlen=capacity)

    def __len__(self) -> int:
        return len(self._items)

    def push(self, snapshot: WorldSnapshot) -> None:
        if self._items and snapshot.tick < self._items[-1].tick:
            raise SnapshotError("snapshot ticks must be non-decreasing")
        if self._items and snapshot.tick == self._items[-1].tick:
            self._items.pop()
        self._items.append(snapshot)

    def capture(self, world) -> WorldSnapshot:
        snapshot = capture(world)
        self.push(snapshot)
        return snapshot

    def ticks(self) -> tuple[int, ...]:
        return tuple(s.tick for s in self._items)

    def latest(self) -> WorldSnapshot:
        if not self._items:
            raise SnapshotError("snapshot ring is empty")
        return self._items[-1]

    def at_or_before(self, tick: int) -> WorldSnapshot:
        for snapshot in reversed(self._items):
            if snapshot.tick <= tick:
                return snapshot
        raise SnapshotError("no retained snapshot at or before tick", context={"tick": tick})

    def rollback(self, world, tick: int) -> WorldSnapshot:
        """Restore the newest snapshot at or before ``tick`` and drop newer ones."""
        snapshot = self.at_or_before(tick)
        while self._items and self._items[-1].tick > snapshot.tick:
            self._items.pop()
        restore(world, snapshot)
        return snapshot


# ---------------------------------------------------------------------------
# EntityStore bridge
# ---------------------------------------------------------------------------
def to_entity_store(world):
    """Export the live world into an authoritative :class:`~.store.EntityStore`.

    Entity ids are the handles' stable text form.  Physical layout and change
    ticks are exported as a value-free hint (``live.layout``), so importing a
    store whose structure is unchanged reproduces the world exactly, including
    iteration order; value edits made in the store are honoured, and
    structural edits fall back to a canonical slot-ordered rebuild.
    Resources are exported as store resources; the RNG, allocator, pending
    events and runtime metadata are exported under reserved ``live.*``
    resource ids so a round trip is exact.
    """
    from .store import EntityStore

    registry = world.components
    store = EntityStore(registry.to_schema_registry())
    with store.transaction():
        for handle in world.iter_entities():
            entity_id = handle_to_text(handle)
            store.create_entity(entity_id)
            for name in world.components_of(handle):
                info = registry.get(name)
                store.set_component(entity_id, name, registry.store_value(info, world.get(handle, name)), version=info.schema.version if info.schema else 1)
        for name in sorted(world.resources):
            store.set_resource(name, copy_value(world.resources[name]))
        store.set_resource("live.rng", world.rng.state())
        store.set_resource("live.allocator", world.entities.snapshot())
        store.set_resource("live.components", registry.catalog())
        store.set_resource("live.events", world.events.to_record())
        store.set_resource("live.layout", _layout_hint(world))
        store.set_resource("live.meta", {"name": world.name, "tick": world.tick, "change_tick": world.change_tick, "meta": copy_value(world.meta)})
        store.advance_tick(world.tick)
    return store


def _layout_hint(world) -> dict[str, Any]:
    """Layout without values: table order, row order, sparse order, change ticks."""
    layout = _layout_payload(world)
    for table in layout["tables"]:
        table.pop("columns")
    for row in layout["sparse"].values():
        row.pop("values")
    return layout


def _exact_payload(store, resources: Mapping[str, Any], components: ComponentRegistry) -> dict[str, Any] | None:
    """Rebuild an exact snapshot payload when the store still matches the
    exported layout structurally (same entities, same component sets).

    Component *values* always come from the store, so value edits made through
    ``EntityStore``/``WorldSession`` are honoured; structural edits fall back to
    the canonical (slot-ordered) rebuild.
    """
    layout = resources.get("live.layout")
    if not isinstance(layout, Mapping) or "live.allocator" not in resources:
        return None
    try:
        store_sets = {handle_from_text(eid): set(store.component_ids(eid)) for eid in store.entity_ids()}
        layout_sets: dict[int, set[str]] = {}
        tables = []
        for table in layout["tables"]:
            columns: dict[str, list[Any]] = {name: [] for name in table["signature"]}
            for handle in table["entities"]:
                layout_sets.setdefault(handle, set()).update(table["signature"])
                eid = handle_to_text(handle)
                for name in table["signature"]:
                    info = components.get(name)
                    columns[name].append(to_json(components.value_from_store(info, store.get_component(eid, name).data)))
            tables.append({**copy_value(table), "columns": columns})
        sparse = {}
        for name, row in layout["sparse"].items():
            info = components.get(name)
            values = []
            for handle in row["entities"]:
                layout_sets.setdefault(handle, set()).add(name)
                values.append(to_json(components.value_from_store(info, store.get_component(handle_to_text(handle), name).data)))
            sparse[name] = {**copy_value(row), "values": values}
        for handle in HandleAllocator.restore(resources["live.allocator"]).alive_handles():
            layout_sets.setdefault(handle, set())
        if layout_sets != store_sets:
            return None
    except (ECSError, KeyError, TypeError, ValueError):  # any mismatch -> canonical rebuild
        return None
    meta = resources.get("live.meta", {})
    return {
        "schema": SNAPSHOT_SCHEMA,
        "name": meta.get("name", "imported"),
        "tick": int(meta.get("tick", store.tick)),
        "change_tick": int(meta.get("change_tick", 0)),
        "components": components.catalog(),
        "allocator": resources["live.allocator"],
        "layout": {**{k: v for k, v in layout.items() if k not in ("tables", "sparse")}, "tables": tables, "sparse": sparse},
        "resources": {k: to_json(v) for k, v in sorted(resources.items()) if not k.startswith("live.")},
        "events": resources.get("live.events", EventBus().to_record()),
        "rng": resources.get("live.rng", DeterministicRng(0).state()),
        "meta": {k: to_json(v) for k, v in sorted((meta.get("meta") or {}).items())},
    }


def from_entity_store(store, *, components: ComponentRegistry | None = None):
    """Build a live world from an ``EntityStore`` produced by :func:`to_entity_store`
    or from any store whose entities use live handle ids.

    Foreign stores (arbitrary string ids) are also accepted when ``live.*``
    resources are absent: entities are then allocated fresh in ascending id
    order and every schema in the store's registry becomes a table component.
    """
    from .live import LiveWorld

    resources = {rid: store.get_resource(rid).value for rid in store.resource_ids()}
    if components is None:
        if "live.components" in resources:
            components = ComponentRegistry.from_catalog(resources["live.components"])
        else:
            components = ComponentRegistry()
            for record in store.registry.catalog():
                if record["schema_id"] not in components:
                    components.register(record["schema_id"], schema=store.registry.get(record["schema_id"]))
    meta = resources.get("live.meta", {"name": "imported", "tick": store.tick})
    exact = _exact_payload(store, resources, components)
    if exact is not None:
        world = LiveWorld(components, name=exact["name"])
        _restore_payload(world, exact)
        return world
    world = LiveWorld(components, name=meta["name"])
    world.tick = int(meta["tick"])
    world.meta = copy_value(meta.get("meta", {}))
    if "live.allocator" in resources:
        world.entities = HandleAllocator.restore(resources["live.allocator"])
        world._loc_table = [-1] * world.entities.slot_count
        world._loc_row = [-1] * world.entities.slot_count
        alive = set(world.entities.alive_handles())
        for entity_id in store.entity_ids():
            handle = handle_from_text(entity_id)
            if handle not in alive:
                raise ValidationError("store entity is not alive in exported allocator", context={"entity_id": entity_id})
            values = {}
            for name in store.component_ids(entity_id):
                info = components.get(name)
                values[name] = components.value_from_store(info, store.get_component(entity_id, name).data)
            world._place_new(handle, world._prepare(values))
        if len(alive) != len(store.entity_ids()):
            raise ValidationError("exported allocator and store entities disagree")
    else:
        for entity_id in store.entity_ids():
            values = {}
            for name in store.component_ids(entity_id):
                info = components.get(name)
                values[name] = components.value_from_store(info, store.get_component(entity_id, name).data)
            world.spawn(values)
    if "live.events" in resources:
        world.events = EventBus.from_record(resources["live.events"])
    if "live.rng" in resources:
        world.rng = DeterministicRng.from_state(resources["live.rng"])
    for rid, value in resources.items():
        if not rid.startswith("live."):
            world.set_resource(rid, value)
    return world


__all__ = [
    "SNAPSHOT_SCHEMA",
    "STATE_SCHEMA",
    "SnapshotRing",
    "WorldSnapshot",
    "capture",
    "decode_snapshot",
    "encode_snapshot",
    "from_entity_store",
    "restore",
    "state_record",
    "to_entity_store",
    "world_from_snapshot",
]
