"""Archetype tables and sparse sets: the live world's physical storage.

Two complementary layouts, chosen per component type (see
:class:`~.components.StorageKind`):

``Table`` (archetype storage)
    Every distinct *set* of table components gets one table.  Each table keeps
    one column (a Python list) per component plus a parallel entity column, so
    iterating "all entities with Position and Velocity" walks contiguous lists
    with no per-entity hashing.  Adding/removing a table component moves the
    entity's row to the neighbouring table; the move target is cached on the
    table as an *edge* so repeated transitions are O(1) lookups.

``SparseSet``
    ``sparse[index] -> dense slot`` plus packed ``dense`` entity/value lists.
    Insert and remove are O(1) (swap-remove) and never move the entity's
    table row, which suits high-churn components.

Both layouts carry per-value change ticks (``added``/``changed``) that power
``added=`` / ``changed=`` query filters.

Row order is part of observable iteration order.  It is deterministic for a
given sequence of operations, and snapshots persist it exactly, so a restored
world iterates identically to the original.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .entities import INDEX_MASK
from .errors import ComponentTypeError, EntityHandleError

MAX_TABLES = 65_536


class Table:
    """One archetype: a fixed, sorted signature of table component ids."""

    __slots__ = ("add_edges", "added", "changed", "columns", "entities", "remove_edges", "signature", "signature_set", "table_id")

    def __init__(self, table_id: int, signature: tuple[int, ...]) -> None:
        self.table_id = table_id
        self.signature = signature
        self.signature_set = frozenset(signature)
        self.entities: list[int] = []
        self.columns: dict[int, list[Any]] = {cid: [] for cid in signature}
        self.added: dict[int, list[int]] = {cid: [] for cid in signature}
        self.changed: dict[int, list[int]] = {cid: [] for cid in signature}
        self.add_edges: dict[int, Table] = {}
        self.remove_edges: dict[int, Table] = {}

    def __len__(self) -> int:
        return len(self.entities)

    def push(self, handle: int, values: dict[int, Any], ticks: dict[int, tuple[int, int]]) -> int:
        """Append a row. ``values``/``ticks`` must cover the whole signature."""
        row = len(self.entities)
        self.entities.append(handle)
        for cid in self.signature:
            self.columns[cid].append(values[cid])
            added, changed = ticks[cid]
            self.added[cid].append(added)
            self.changed[cid].append(changed)
        return row

    def swap_remove(self, row: int) -> int | None:
        """Remove ``row``; return the handle that moved into it (if any)."""
        last = len(self.entities) - 1
        if row < 0 or row > last:
            raise EntityHandleError("table row out of range", context={"row": row, "table": self.table_id})
        moved: int | None = None
        if row != last:
            moved = self.entities[last]
            self.entities[row] = moved
            for cid in self.signature:
                column = self.columns[cid]
                column[row] = column[last]
                added = self.added[cid]
                added[row] = added[last]
                changed = self.changed[cid]
                changed[row] = changed[last]
        self.entities.pop()
        for cid in self.signature:
            self.columns[cid].pop()
            self.added[cid].pop()
            self.changed[cid].pop()
        return moved

    def take_row(self, row: int) -> tuple[dict[int, Any], dict[int, tuple[int, int]]]:
        values = {cid: self.columns[cid][row] for cid in self.signature}
        ticks = {cid: (self.added[cid][row], self.changed[cid][row]) for cid in self.signature}
        return values, ticks


class ArchetypeGraph:
    """All tables of a world, indexed by signature, with a creation generation.

    ``generation`` increases whenever a table is created; queries cache their
    matched table list and refresh only when it changes.
    """

    __slots__ = ("_by_signature", "generation", "tables")

    def __init__(self) -> None:
        self.tables: list[Table] = []
        self._by_signature: dict[tuple[int, ...], Table] = {}
        self.generation = 0
        self.get_or_create(())

    @property
    def empty(self) -> Table:
        return self.tables[0]

    def get(self, signature: tuple[int, ...]) -> Table | None:
        return self._by_signature.get(signature)

    def get_or_create(self, signature: tuple[int, ...]) -> Table:
        table = self._by_signature.get(signature)
        if table is not None:
            return table
        if len(self.tables) >= MAX_TABLES:
            raise ComponentTypeError("archetype table bound exceeded", context={"maximum": MAX_TABLES})
        if list(signature) != sorted(set(signature)):
            raise ComponentTypeError("table signature must be sorted and unique")
        table = Table(len(self.tables), signature)
        self.tables.append(table)
        self._by_signature[signature] = table
        self.generation += 1
        return table

    def with_component(self, table: Table, cid: int) -> Table:
        target = table.add_edges.get(cid)
        if target is None:
            target = self.get_or_create(tuple(sorted(table.signature_set | {cid})))
            table.add_edges[cid] = target
            target.remove_edges[cid] = table
        return target

    def without_component(self, table: Table, cid: int) -> Table:
        target = table.remove_edges.get(cid)
        if target is None:
            target = self.get_or_create(tuple(sorted(table.signature_set - {cid})))
            table.remove_edges[cid] = target
            target.add_edges[cid] = table
        return target

    def matching(self, required: frozenset[int], excluded: frozenset[int]) -> list[Table]:
        return [
            table
            for table in self.tables
            if required <= table.signature_set and not (excluded & table.signature_set)
        ]


class SparseSet:
    """Packed sparse set keyed by entity slot index, storing the full handle."""

    __slots__ = ("added", "changed", "component_id", "entities", "sparse", "values")

    def __init__(self, component_id: int) -> None:
        self.component_id = component_id
        self.sparse: dict[int, int] = {}
        self.entities: list[int] = []
        self.values: list[Any] = []
        self.added: list[int] = []
        self.changed: list[int] = []

    def __len__(self) -> int:
        return len(self.entities)

    def __contains__(self, handle: object) -> bool:
        if not isinstance(handle, int):
            return False
        slot = self.sparse.get(handle & INDEX_MASK)
        return slot is not None and self.entities[slot] == handle

    def slot(self, handle: int) -> int | None:
        slot = self.sparse.get(handle & INDEX_MASK)
        if slot is None or self.entities[slot] != handle:
            return None
        return slot

    def insert(self, handle: int, value: Any, tick: int) -> bool:
        """Insert or replace; returns ``True`` when the value is new."""
        slot = self.slot(handle)
        if slot is not None:
            self.values[slot] = value
            self.changed[slot] = tick
            return False
        self.sparse[handle & INDEX_MASK] = len(self.entities)
        self.entities.append(handle)
        self.values.append(value)
        self.added.append(tick)
        self.changed.append(tick)
        return True

    def restore_row(self, handle: int, value: Any, added: int, changed: int) -> None:
        if self.slot(handle) is not None:
            raise EntityHandleError("duplicate sparse row", context={"component_id": self.component_id})
        self.sparse[handle & INDEX_MASK] = len(self.entities)
        self.entities.append(handle)
        self.values.append(value)
        self.added.append(added)
        self.changed.append(changed)

    def get(self, handle: int) -> Any:
        slot = self.slot(handle)
        if slot is None:
            raise KeyError(handle)
        return self.values[slot]

    def remove(self, handle: int) -> Any:
        slot = self.slot(handle)
        if slot is None:
            raise KeyError(handle)
        value = self.values[slot]
        last = len(self.entities) - 1
        if slot != last:
            moved = self.entities[last]
            self.entities[slot] = moved
            self.values[slot] = self.values[last]
            self.added[slot] = self.added[last]
            self.changed[slot] = self.changed[last]
            self.sparse[moved & INDEX_MASK] = slot
        self.entities.pop()
        self.values.pop()
        self.added.pop()
        self.changed.pop()
        del self.sparse[handle & INDEX_MASK]
        return value

    def mark_changed(self, handle: int, tick: int) -> None:
        slot = self.slot(handle)
        if slot is None:
            raise KeyError(handle)
        self.changed[slot] = tick

    def items(self) -> Iterator[tuple[int, Any]]:
        return zip(list(self.entities), list(self.values))


__all__ = ["MAX_TABLES", "ArchetypeGraph", "SparseSet", "Table"]
