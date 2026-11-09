"""The live ECS world: dense entities, archetype/sparse storage, resources, events.

:class:`LiveWorld` is the per-tick game runtime.  It complements rather than
replaces the authoritative :class:`~.store.EntityStore`:

===========================  ==============================================
``EntityStore``              ``LiveWorld``
===========================  ==============================================
string ids, revisions        packed generational int handles
dict-of-records              archetype tables + sparse sets
every write deep-copied      values owned in place; change ticks instead
evidence / diff / sessions   hot loop / scheduler / scripts
===========================  ==============================================

The two are bridged losslessly by :mod:`.live_snapshot`
(``to_entity_store`` / ``from_entity_store``) so a live simulation can be
checkpointed into a :class:`~.world.WorldSession`, diffed and inspected with
the existing tooling.

Change detection uses a monotonically increasing ``change_tick``: the
scheduler bumps it before every system run and stamps writes with it, and a
system's ``added=``/``changed=`` query filters compare against the tick of
that system's previous run.  This is exact regardless of system order within
a tick (the classic "changed later in the previous frame" case included).

Structural changes (spawn/despawn/add/remove component) are rejected while a
query iterator is active; use :meth:`commands` to defer them.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from .channels import EventBus, EventReader, EventRecord
from .components import ComponentInfo, ComponentRegistry, StorageKind
from .entities import (
    INDEX_MASK,
    MAX_LIVE_ENTITIES,
    HandleAllocator,
    handle_to_text,
)
from .errors import (
    ComponentNotFoundError,
    EntityHandleError,
    ResourceNotFoundError,
    StructuralChangeError,
    ValidationError,
)
from .rng import DeterministicRng
from .storage import ArchetypeGraph, SparseSet, Table
from .values import canonical_copy, check_value, copy_value

_MISSING = object()
_WORLD_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MAX_RESOURCES = 4096


class LiveWorld:
    def __init__(
        self,
        components: ComponentRegistry | None = None,
        *,
        name: str = "world",
        seed: int | str = 0,
        capacity: int = MAX_LIVE_ENTITIES,
    ) -> None:
        if not isinstance(name, str) or not _WORLD_NAME_RE.fullmatch(name):
            raise ValidationError("invalid world name", context={"name": name})
        self.name = name
        self.components = components if components is not None else ComponentRegistry()
        self.entities = HandleAllocator(capacity)
        self.graph = ArchetypeGraph()
        self.sparse: dict[int, SparseSet] = {}
        self._loc_table: list[int] = []
        self._loc_row: list[int] = []
        self.resources: dict[str, Any] = {}
        self.events = EventBus()
        self.rng = DeterministicRng(seed)
        self.tick = 0
        self.change_tick = 0
        self._iterating = 0
        self._removed: dict[int, list[int]] = {}
        self._removed_previous: dict[int, list[int]] = {}
        # Plain-data runtime metadata that must survive snapshots (for example
        # the scheduler's per-system last-run change ticks).
        self.meta: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # registration
    # ------------------------------------------------------------------
    def register_component(self, name: str, **kwargs: Any) -> ComponentInfo:
        info = self.components.register(name, **kwargs)
        self._ensure_sparse(info)
        return info

    def _ensure_sparse(self, info: ComponentInfo) -> None:
        if info.storage is StorageKind.SPARSE and info.component_id not in self.sparse:
            self.sparse[info.component_id] = SparseSet(info.component_id)

    def register_event(self, channel: str, *, capacity: int | None = None) -> None:
        if capacity is None:
            self.events.register(channel)
        else:
            self.events.register(channel, capacity=capacity)

    def info(self, name: str) -> ComponentInfo:
        info = self.components.get(name)
        self._ensure_sparse(info)
        return info

    # ------------------------------------------------------------------
    # guards / locations
    # ------------------------------------------------------------------
    def _structural(self) -> None:
        if self._iterating:
            raise StructuralChangeError(
                "structural change during query iteration; use world.commands()",
                context={"world": self.name},
            )

    def _ensure_slot(self, index: int) -> None:
        while len(self._loc_table) <= index:
            self._loc_table.append(-1)
            self._loc_row.append(-1)

    def _location(self, handle: int) -> tuple[Table, int]:
        self.entities.require_alive(handle)
        index = handle & INDEX_MASK
        return self.graph.tables[self._loc_table[index]], self._loc_row[index]

    def _set_location(self, handle: int, table: Table, row: int) -> None:
        index = handle & INDEX_MASK
        self._loc_table[index] = table.table_id
        self._loc_row[index] = row

    def table_of(self, handle: int) -> Table:
        return self._location(handle)[0]

    # ------------------------------------------------------------------
    # entities
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return self.entities.alive_count

    @property
    def entity_count(self) -> int:
        return self.entities.alive_count

    def is_alive(self, handle: Any) -> bool:
        return self.entities.is_alive(handle)

    def iter_entities(self) -> Iterator[int]:
        return self.entities.alive_handles()

    def entity_list(self) -> list[int]:
        return list(self.entities.alive_handles())

    def spawn(self, components: Mapping[str, Any] | None = None) -> int:
        self._structural()
        prepared = self._prepare(components or {})
        handle = self.entities.allocate()
        self._place_new(handle, prepared)
        return handle

    def spawn_batch(self, rows: Iterable[Mapping[str, Any]]) -> list[int]:
        self._structural()
        prepared_rows = [self._prepare(row) for row in rows]
        return [self._place_new(self.entities.allocate(), prepared) for prepared in prepared_rows]

    def _commit_reserved(self, handle: int, components: Mapping[str, Any]) -> int:
        """Materialise a handle reserved by a command queue."""
        self._structural()
        prepared = self._prepare(components)
        self.entities.commit(handle)
        return self._place_new(handle, prepared)

    def _prepare(self, components: Mapping[str, Any]) -> list[tuple[ComponentInfo, Any]]:
        if not isinstance(components, Mapping):
            raise ValidationError("spawn components must be a mapping of name -> value")
        prepared = []
        for name in components:
            info = self.info(name)
            prepared.append((info, self.components.normalise(name, components[name], info=info)))
        return prepared

    def _place_new(self, handle: int, prepared: list[tuple[ComponentInfo, Any]]) -> int:
        tick = self.change_tick
        table_values: dict[int, Any] = {}
        for info, value in prepared:
            if info.storage is StorageKind.TABLE:
                table_values[info.component_id] = value
        signature = tuple(sorted(table_values))
        table = self.graph.get_or_create(signature)
        self._ensure_slot(handle & INDEX_MASK)
        row = table.push(handle, table_values, {cid: (tick, tick) for cid in signature})
        self._set_location(handle, table, row)
        for info, value in prepared:
            if info.storage is StorageKind.SPARSE:
                self.sparse[info.component_id].insert(handle, value, tick)
        return handle

    def despawn(self, handle: int) -> None:
        self._structural()
        table, row = self._location(handle)
        for cid in table.signature:
            self._removed.setdefault(cid, []).append(handle)
        moved = table.swap_remove(row)
        if moved is not None:
            self._set_location(moved, table, row)
        for cid in sorted(self.sparse):
            sparse = self.sparse[cid]
            if handle in sparse:
                sparse.remove(handle)
                self._removed.setdefault(cid, []).append(handle)
        index = handle & INDEX_MASK
        self._loc_table[index] = -1
        self._loc_row[index] = -1
        self.entities.release(handle)

    # ------------------------------------------------------------------
    # components
    # ------------------------------------------------------------------
    def insert(self, handle: int, name: str, value: Any = None) -> None:
        """Add or replace component ``name`` on ``handle`` (validated)."""
        info = self.info(name)
        value = self.components.normalise(name, value, info=info)
        self._insert_normalised(handle, info, value)

    def insert_many(self, handle: int, components: Mapping[str, Any]) -> None:
        for info, value in self._prepare(components):
            self._insert_normalised(handle, info, value)

    def _insert_normalised(self, handle: int, info: ComponentInfo, value: Any) -> None:
        table, row = self._location(handle)
        cid = info.component_id
        tick = self.change_tick
        if info.storage is StorageKind.SPARSE:
            sparse = self.sparse[cid]
            if handle not in sparse:
                self._structural()
            sparse.insert(handle, value, tick)
            return
        if cid in table.signature_set:
            table.columns[cid][row] = value
            table.changed[cid][row] = tick
            return
        self._structural()
        target = self.graph.with_component(table, cid)
        values, ticks = table.take_row(row)
        values[cid] = value
        ticks[cid] = (tick, tick)
        self._move(handle, table, row, target, values, ticks)

    def _move(self, handle: int, source: Table, row: int, target: Table, values: dict, ticks: dict) -> None:
        moved = source.swap_remove(row)
        if moved is not None:
            self._set_location(moved, source, row)
        new_row = target.push(handle, values, ticks)
        self._set_location(handle, target, new_row)

    def remove(self, handle: int, name: str) -> Any:
        info = self.info(name)
        table, row = self._location(handle)
        cid = info.component_id
        if info.storage is StorageKind.SPARSE:
            sparse = self.sparse[cid]
            if handle not in sparse:
                raise ComponentNotFoundError("component not present", context={"entity": handle_to_text(handle), "component": name})
            self._structural()
            value = sparse.remove(handle)
        else:
            if cid not in table.signature_set:
                raise ComponentNotFoundError("component not present", context={"entity": handle_to_text(handle), "component": name})
            self._structural()
            target = self.graph.without_component(table, cid)
            values, ticks = table.take_row(row)
            value = values.pop(cid)
            ticks.pop(cid)
            self._move(handle, table, row, target, values, ticks)
        self._removed.setdefault(cid, []).append(handle)
        return value

    def has(self, handle: int, name: str) -> bool:
        if not self.entities.is_alive(handle):
            return False
        info = self.info(name)
        if info.storage is StorageKind.SPARSE:
            return handle in self.sparse[info.component_id]
        index = handle & INDEX_MASK
        return info.component_id in self.graph.tables[self._loc_table[index]].signature_set

    def get(self, handle: int, name: str, default: Any = _MISSING) -> Any:
        """Return the stored value (treat as read-only; see :meth:`get_mut`)."""
        info = self.info(name)
        if not self.entities.is_alive(handle):
            if default is not _MISSING:
                return default
            self.entities.require_alive(handle)
        cid = info.component_id
        if info.storage is StorageKind.SPARSE:
            sparse = self.sparse[cid]
            slot = sparse.slot(handle)
            if slot is not None:
                return sparse.values[slot]
        else:
            index = handle & INDEX_MASK
            table = self.graph.tables[self._loc_table[index]]
            if cid in table.signature_set:
                return table.columns[cid][self._loc_row[index]]
        if default is not _MISSING:
            return default
        raise ComponentNotFoundError("component not present", context={"entity": handle_to_text(handle), "component": name})

    def get_mut(self, handle: int, name: str) -> Any:
        """Return the stored value and stamp it changed (for in-place edits)."""
        value = self.get(handle, name)
        self.mark_changed(handle, name)
        return value

    def mark_changed(self, handle: int, name: str) -> None:
        info = self.info(name)
        cid = info.component_id
        if info.storage is StorageKind.SPARSE:
            try:
                self.sparse[cid].mark_changed(handle, self.change_tick)
            except KeyError:
                raise ComponentNotFoundError("component not present", context={"entity": handle_to_text(handle), "component": name}) from None
            return
        table, row = self._location(handle)
        if cid not in table.signature_set:
            raise ComponentNotFoundError("component not present", context={"entity": handle_to_text(handle), "component": name})
        table.changed[cid][row] = self.change_tick

    def patch(self, handle: int, name: str, fields: Mapping[str, Any]) -> Any:
        """Merge ``fields`` into a mapping component and re-validate."""
        current = self.get(handle, name)
        if not isinstance(current, dict) or not isinstance(fields, Mapping):
            raise ValidationError("patch requires a mapping component and mapping fields", context={"component": name})
        merged = dict(current)
        merged.update(fields)
        self.insert(handle, name, merged)
        return self.get(handle, name)

    def component_ticks(self, handle: int, name: str) -> tuple[int, int]:
        """``(added_tick, changed_tick)`` of a component value."""
        info = self.info(name)
        cid = info.component_id
        if info.storage is StorageKind.SPARSE:
            sparse = self.sparse[cid]
            slot = sparse.slot(handle)
            if slot is None:
                raise ComponentNotFoundError("component not present", context={"component": name})
            return sparse.added[slot], sparse.changed[slot]
        table, row = self._location(handle)
        if cid not in table.signature_set:
            raise ComponentNotFoundError("component not present", context={"component": name})
        return table.added[cid][row], table.changed[cid][row]

    def components_of(self, handle: int) -> tuple[str, ...]:
        table, _ = self._location(handle)
        names = [self.components.by_id(cid).name for cid in table.signature]
        for cid in sorted(self.sparse):
            if handle in self.sparse[cid]:
                names.append(self.components.by_id(cid).name)
        return tuple(sorted(names))

    def entity_view(self, handle: int) -> dict[str, Any]:
        """Copy of every component on ``handle`` keyed by name."""
        return {name: copy_value(self.get(handle, name)) for name in self.components_of(handle)}

    def removed(self, name: str) -> tuple[int, ...]:
        """Handles that lost ``name`` (or were despawned) this tick or last tick.

        Removal trackers are double-buffered like events, so a system observes
        a removal whether it runs before or after the remover within a tick.
        """
        cid = self.info(name).component_id
        return tuple(self._removed_previous.get(cid, ())) + tuple(self._removed.get(cid, ()))

    def clear_trackers(self) -> None:
        """Age removal trackers by one tick (called by the scheduler)."""
        self._removed_previous = self._removed
        self._removed = {}

    # ------------------------------------------------------------------
    # queries / commands
    # ------------------------------------------------------------------
    def query(self, *fetch: str, **filters: Any):
        from .live_query import Query

        return Query(self, fetch, **filters)

    def commands(self):
        from .deferred import CommandQueue

        return CommandQueue(self)

    # ------------------------------------------------------------------
    # resources
    # ------------------------------------------------------------------
    def set_resource(self, name: str, value: Any) -> None:
        if not isinstance(name, str) or not name or len(name) > 128:
            raise ValidationError("resource name must be 1..128 chars")
        if name not in self.resources and len(self.resources) >= MAX_RESOURCES:
            raise ValidationError("resource bound exceeded", context={"maximum": MAX_RESOURCES})
        check_value(value, label=f"resource {name}")
        self.resources[name] = canonical_copy(value)

    def get_resource(self, name: str, default: Any = _MISSING) -> Any:
        if name in self.resources:
            return self.resources[name]
        if default is not _MISSING:
            return default
        raise ResourceNotFoundError("resource not found", context={"resource_id": name})

    def has_resource(self, name: str) -> bool:
        return name in self.resources

    def remove_resource(self, name: str) -> Any:
        if name not in self.resources:
            raise ResourceNotFoundError("resource not found", context={"resource_id": name})
        return self.resources.pop(name)

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    def send(self, channel: str, payload: Any) -> EventRecord:
        if not self.events.has(channel):
            self.events.register(channel)
        return self.events.send(channel, payload, tick=self.tick)

    def reader(self, channel: str, reader_id: str) -> EventReader:
        if not self.events.has(channel):
            self.events.register(channel)
        return self.events.reader(channel, reader_id)

    # ------------------------------------------------------------------
    # state identity
    # ------------------------------------------------------------------
    def state_record(self) -> dict[str, Any]:
        """Layout-independent game state (what the digest is defined over)."""
        from .live_snapshot import state_record

        return state_record(self)

    @property
    def state_digest(self) -> str:
        from .canonical import digest

        return digest(self.state_record())

    def snapshot(self):
        from .live_snapshot import capture

        return capture(self)

    def restore(self, snapshot) -> None:
        from .live_snapshot import restore

        restore(self, snapshot)

    def check_integrity(self) -> None:
        """Verify storage invariants; raises on corruption (used by tests/tools)."""
        alive = set(self.entities.alive_handles())
        seen: set[int] = set()
        for table in self.graph.tables:
            for cid in table.signature:
                if len(table.columns[cid]) != len(table.entities):
                    raise EntityHandleError("column length mismatch", context={"table": table.table_id})
            for row, handle in enumerate(table.entities):
                if handle not in alive or handle in seen:
                    raise EntityHandleError("table holds a dead or duplicate entity", context={"table": table.table_id})
                seen.add(handle)
                index = handle & INDEX_MASK
                if self._loc_table[index] != table.table_id or self._loc_row[index] != row:
                    raise EntityHandleError("entity location map is stale", context={"entity": handle_to_text(handle)})
        if seen != alive:
            raise EntityHandleError("alive entities missing from tables")
        for cid, sparse in self.sparse.items():
            for slot, handle in enumerate(sparse.entities):
                if handle not in alive or sparse.sparse.get(handle & INDEX_MASK) != slot:
                    raise EntityHandleError("sparse set is inconsistent", context={"component_id": cid})


__all__ = ["MAX_RESOURCES", "LiveWorld"]
