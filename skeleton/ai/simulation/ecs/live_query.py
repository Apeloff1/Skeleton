"""Cached, deterministic queries over the live world.

``world.query("position", "velocity", without=("frozen",), changed=("velocity",))``

Terms
    positional ``fetch``  required components whose values are yielded
    ``optional=``         yielded when present, ``None`` otherwise
    ``with_=``            required but not yielded (filters/markers)
    ``without=``          must be absent
    ``added=``            required, and added after ``since``
    ``changed=``          required, and added-or-changed after ``since``
    ``mut=``              subset of fetched names stamped *changed* as yielded
    ``since=``            change tick the added/changed filters compare to

Matching tables are cached per query and refreshed only when the archetype
graph grows.  Iteration order is table-creation order then row order, which
is deterministic and preserved by snapshots.  ``ordered=True`` instead
yields in ascending entity-slot order, independent of storage layout.

While an iterator is live the world rejects structural changes.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import TYPE_CHECKING, Any

from .components import StorageKind
from .entities import INDEX_MASK, handle_to_text
from .errors import ComponentNotFoundError, EntityHandleError, QueryError

if TYPE_CHECKING:  # pragma: no cover
    from .live import LiveWorld

MAX_QUERY_TERMS = 64


def _names(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, str):
        value = (value,)
    try:
        names = tuple(value)
    except TypeError:
        raise QueryError(f"{label} must be a sequence of component names") from None
    for name in names:
        if not isinstance(name, str):
            raise QueryError(f"{label} entries must be component names")
    return names


class Query:
    __slots__ = (
        "_added_ids",
        "_cache_generation",
        "_cache_graph",
        "_changed_ids",
        "_ex_sparse",
        "_ex_table",
        "_fetch_ids",
        "_mut_ids",
        "_optional_ids",
        "_req_sparse",
        "_req_table",
        "_tables",
        "added",
        "changed",
        "fetch",
        "mut",
        "optional",
        "ordered",
        "since",
        "with_",
        "without",
        "world",
    )

    def __init__(
        self,
        world: LiveWorld,
        fetch: Iterable[str],
        *,
        optional: Iterable[str] = (),
        with_: Iterable[str] = (),
        without: Iterable[str] = (),
        added: Iterable[str] = (),
        changed: Iterable[str] = (),
        mut: Iterable[str] = (),
        since: int | None = None,
        ordered: bool = False,
    ) -> None:
        self.world = world
        self.fetch = _names(fetch, "fetch")
        self.optional = _names(optional, "optional")
        self.with_ = _names(with_, "with_")
        self.without = _names(without, "without")
        self.added = _names(added, "added")
        self.changed = _names(changed, "changed")
        self.mut = _names(mut, "mut")
        total = sum(len(t) for t in (self.fetch, self.optional, self.with_, self.without, self.added, self.changed))
        if total > MAX_QUERY_TERMS:
            raise QueryError("too many query terms", context={"maximum": MAX_QUERY_TERMS})
        if len(set(self.fetch + self.optional)) != len(self.fetch) + len(self.optional):
            raise QueryError("a component may be fetched only once")
        required = set(self.fetch) | set(self.with_) | set(self.added) | set(self.changed)
        if required & set(self.without):
            raise QueryError("a component cannot be both required and excluded", context={"names": sorted(required & set(self.without))})
        if not set(self.mut) <= set(self.fetch) | set(self.optional):
            raise QueryError("mut= names must also be fetched")
        if since is not None and (isinstance(since, bool) or not isinstance(since, int)):
            raise QueryError("since must be an integer change tick")
        if (self.added or self.changed) and since is None:
            since = -1
        self.since = since
        self.ordered = bool(ordered)

        infos = {name: world.info(name) for name in set(self.fetch) | set(self.optional) | required | set(self.without)}
        self._fetch_ids = tuple(infos[n].component_id for n in self.fetch)
        self._optional_ids = tuple(infos[n].component_id for n in self.optional)
        self._req_table = frozenset(infos[n].component_id for n in required if infos[n].storage is StorageKind.TABLE)
        self._req_sparse = tuple(sorted(infos[n].component_id for n in required if infos[n].storage is StorageKind.SPARSE))
        self._ex_table = frozenset(infos[n].component_id for n in self.without if infos[n].storage is StorageKind.TABLE)
        self._ex_sparse = tuple(sorted(infos[n].component_id for n in self.without if infos[n].storage is StorageKind.SPARSE))
        self._added_ids = tuple(infos[n].component_id for n in self.added)
        self._changed_ids = tuple(infos[n].component_id for n in self.changed)
        self._mut_ids = frozenset(infos[n].component_id for n in self.mut)
        self._cache_generation = -1
        self._cache_graph = None
        self._tables: list = []

    # ------------------------------------------------------------------
    def _matched_tables(self) -> list:
        graph = self.world.graph
        # A restore swaps the whole graph object, so identity is checked too.
        if graph is not self._cache_graph or graph.generation != self._cache_generation:
            self._tables = graph.matching(self._req_table, self._ex_table)
            self._cache_generation = graph.generation
            self._cache_graph = graph
        return self._tables

    def _value(self, table, row: int, handle: int, cid: int, required: bool) -> tuple[bool, Any]:
        if cid in table.signature_set:
            return True, table.columns[cid][row]
        sparse = self.world.sparse.get(cid)
        if sparse is not None:
            slot = sparse.slot(handle)
            if slot is not None:
                return True, sparse.values[slot]
        return False, None

    def _ticks(self, table, row: int, handle: int, cid: int) -> tuple[int, int]:
        if cid in table.signature_set:
            return table.added[cid][row], table.changed[cid][row]
        sparse = self.world.sparse[cid]
        slot = sparse.slot(handle)
        return sparse.added[slot], sparse.changed[slot]

    def _accept(self, table, row: int, handle: int) -> bool:
        sparse_sets = self.world.sparse
        for cid in self._req_sparse:
            if handle not in sparse_sets[cid]:
                return False
        for cid in self._ex_sparse:
            if handle in sparse_sets[cid]:
                return False
        since = self.since
        if since is not None:
            for cid in self._added_ids:
                if self._ticks(table, row, handle, cid)[0] <= since:
                    return False
            for cid in self._changed_ids:
                if self._ticks(table, row, handle, cid)[1] <= since:
                    return False
        return True

    def _emit(self, table, row: int, handle: int) -> tuple:
        out = [handle]
        stamp = self.world.change_tick
        mut = self._mut_ids
        for cid in self._fetch_ids:
            if cid in table.signature_set:
                out.append(table.columns[cid][row])
                if cid in mut:
                    table.changed[cid][row] = stamp
            else:
                sparse = self.world.sparse[cid]
                slot = sparse.slot(handle)
                out.append(sparse.values[slot])
                if cid in mut:
                    sparse.changed[slot] = stamp
        for cid in self._optional_ids:
            present, value = self._value(table, row, handle, cid, False)
            out.append(value)
            if present and cid in mut:
                if cid in table.signature_set:
                    table.changed[cid][row] = stamp
                else:
                    self.world.sparse[cid].mark_changed(handle, stamp)
        return tuple(out)

    def _candidates(self) -> Iterator[tuple[Any, int, int]]:
        world = self.world
        if self.ordered:
            tables = {t.table_id: t for t in self._matched_tables()}
            for handle in world.iter_entities():
                index = handle & INDEX_MASK
                table = tables.get(world._loc_table[index])
                if table is not None:
                    yield table, world._loc_row[index], handle
            return
        if not self._req_table and self._req_sparse:
            # Drive from the smallest required sparse set.
            smallest = min((world.sparse[cid] for cid in self._req_sparse), key=len)
            for handle in list(smallest.entities):
                index = handle & INDEX_MASK
                table = world.graph.tables[world._loc_table[index]]
                if self._ex_table & table.signature_set:
                    continue
                yield table, world._loc_row[index], handle
            return
        for table in self._matched_tables():
            entities = table.entities
            for row in range(len(entities)):
                yield table, row, entities[row]

    def __iter__(self) -> Iterator[tuple]:
        world = self.world
        world._iterating += 1
        try:
            for table, row, handle in self._candidates():
                if self._accept(table, row, handle):
                    yield self._emit(table, row, handle)
        finally:
            world._iterating -= 1

    # ------------------------------------------------------------------
    def rows(self) -> list[tuple]:
        """Materialise matches (safe to mutate the world structurally after)."""
        return list(self)

    def entities(self) -> list[int]:
        world = self.world
        world._iterating += 1
        try:
            return [h for t, r, h in self._candidates() if self._accept(t, r, h)]
        finally:
            world._iterating -= 1

    def count(self) -> int:
        return len(self.entities())

    def is_empty(self) -> bool:
        for _ in self.entities():
            return False
        return True

    def single(self) -> tuple:
        rows = self.rows()
        if len(rows) != 1:
            raise QueryError("query expected exactly one match", context={"matches": len(rows)})
        return rows[0]

    def first(self, default: Any = None) -> Any:
        rows = self.rows()
        return rows[0] if rows else default

    def contains(self, handle: int) -> bool:
        world = self.world
        if not world.is_alive(handle):
            return False
        index = handle & INDEX_MASK
        table = world.graph.tables[world._loc_table[index]]
        if not self._req_table <= table.signature_set or self._ex_table & table.signature_set:
            return False
        return self._accept(table, world._loc_row[index], handle)

    def get(self, handle: int) -> tuple:
        world = self.world
        if not world.is_alive(handle):
            raise EntityHandleError("entity is not alive", context={"entity": handle_to_text(handle) if isinstance(handle, int) and handle >= 0 else repr(handle)})
        if not self.contains(handle):
            raise ComponentNotFoundError("entity does not match query", context={"entity": handle_to_text(handle)})
        index = handle & INDEX_MASK
        return self._emit(world.graph.tables[world._loc_table[index]], world._loc_row[index], handle)

    def for_each(self, fn: Callable[..., Any]) -> int:
        count = 0
        for row in self:
            fn(*row)
            count += 1
        return count

    def matched_table_ids(self) -> tuple[int, ...]:
        return tuple(t.table_id for t in self._matched_tables())


__all__ = ["MAX_QUERY_TERMS", "Query"]
