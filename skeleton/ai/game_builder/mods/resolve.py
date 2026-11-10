"""Load order and dependency resolution with conflict detection."""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Iterable

from .manifest import ModError, ModManifest

MAX_RESOLVE_MODS = 2048
MAX_RESOLVE_REFERENCES = MAX_RESOLVE_MODS * 64


class ResolveError(ModError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class LoadPlan:
    order: tuple[ModManifest, ...]
    skipped: tuple[str, ...] = ()  # disabled mods the order did not need

    def ids(self) -> list[str]:
        return [m.mod_id for m in self.order]


def resolve_load_order(mods: Iterable[ModManifest]) -> LoadPlan:
    """Deterministic topological order. Edges: dependency -> dependent, ``load_after``,
    ``load_before`` and installed ``optional`` deps. Ties break by mod id.

    Raises ``ResolveError`` listing every problem: duplicate ids, missing or
    version-mismatched (optional too, when installed) dependencies, declared
    conflicts, and ordering cycles.
    """
    problems: list[str] = []
    by_id: dict[str, ModManifest] = {}
    try:
        for count, m in enumerate(mods, 1):
            if count > MAX_RESOLVE_MODS:
                raise ResolveError(["mod count exceeds resolver bound"])
            if type(m) is not ModManifest:
                raise ResolveError(["invalid mod manifest in resolver input"])
            if m.mod_id in by_id:
                problems.append(f"duplicate mod {m.mod_id}")
            by_id[m.mod_id] = m
    except ResolveError:
        raise
    except Exception:
        # Inventory iterators may fail after yielding otherwise valid mods.
        # Convert that failure into a typed, fail-closed admission result.
        raise ResolveError(["mod inventory iterator failed"]) from None
    # Directly constructed ModManifest values can bypass from_dict limits.
    # Bound the total graph edge inventory before materializing adjacency.
    references = sum(len(m.depends) + len(m.optional) + len(m.conflicts)
                     + len(m.load_after) + len(m.load_before) for m in by_id.values())
    if references > MAX_RESOLVE_REFERENCES:
        raise ResolveError(["mod dependency graph exceeds resolver bound"])
    edges: dict[str, set[str]] = {k: set() for k in by_id}
    conflicts: set[tuple[str, ...]] = set()
    for m in by_id.values():
        for dep, spec in sorted(m.depends.items()):
            got = by_id.get(dep)
            if got is None:
                problems.append(f"{m.mod_id} requires missing {dep} {spec}")
            elif not spec.matches(got.version):
                problems.append(f"{m.mod_id} requires {dep} {spec}, found {got.version}")
            else:
                edges[dep].add(m.mod_id)
        for dep, spec in sorted(m.optional.items()):
            got = by_id.get(dep)
            if got is not None:
                if not spec.matches(got.version):
                    problems.append(f"{m.mod_id} optional {dep} {spec}, found {got.version}")
                else:
                    edges[dep].add(m.mod_id)
        for other in m.conflicts:
            if other in by_id:
                conflicts.add(tuple(sorted((m.mod_id, other))))
        for a in m.load_after:
            if a in by_id:
                edges[a].add(m.mod_id)
        for b in m.load_before:
            if b in by_id:
                edges[m.mod_id].add(b)
    problems += [f"{a} conflicts with {b}" for a, b in sorted(conflicts)]
    indeg = {k: 0 for k in by_id}
    for src in edges:
        for dst in edges[src]:
            indeg[dst] += 1
    heap = [k for k, d in indeg.items() if d == 0]
    heapq.heapify(heap)
    order: list[str] = []
    while heap:
        k = heapq.heappop(heap)
        order.append(k)
        for dst in sorted(edges[k]):
            indeg[dst] -= 1
            if indeg[dst] == 0:
                heapq.heappush(heap, dst)
    if len(order) != len(by_id):
        stuck = sorted(k for k in by_id if k not in order)
        problems.append(f"load-order cycle among {stuck}")
    if problems:
        raise ResolveError(problems)
    return LoadPlan(tuple(by_id[k] for k in order))


def ordered_before(plan: LoadPlan, earlier: str, later: str) -> bool:
    """True when ``later`` explicitly orders itself after ``earlier`` (dep or load_after)."""
    m = {x.mod_id: x for x in plan.order}
    seen, stack = set(), [later]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in m:
            continue
        seen.add(cur)
        x = m[cur]
        nxt = set(x.depends) | set(x.optional) | set(x.load_after)
        nxt |= {o.mod_id for o in plan.order if cur in o.load_before}
        if earlier in nxt:
            return True
        stack.extend(nxt)
    return False
