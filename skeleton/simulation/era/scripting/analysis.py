"""Room-graph analysis and campaign checks for era data (STU-ERAS slice 3).

Runs on already-validated :class:`EraSpec` objects, so the schema stays the
single structural gate. This layer adds *semantic* checks the schema cannot
express on one field at a time: reachability from ``start``, one-way exits,
dead ends, boss placement, and cross-era ordering. Pure, deterministic,
stdlib-only; traversal always follows :data:`DIRECTIONS` order so results are
stable across runs and platforms.

Findings carry a severity. ``error`` findings make :func:`assert_clean` raise
:class:`SchemaError` (fail-closed); ``warning`` findings are advisory.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable

from skeleton.simulation.era.scripting.schema import (
    DIRECTIONS,
    OPPOSITE,
    EraSpec,
    SchemaError,
)

ERROR = "error"
WARNING = "warning"
TERMINAL_KINDS = ("boss", "secret")


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    detail: str
    severity: str = ERROR

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "path": self.path,
            "detail": self.detail,
            "severity": self.severity,
        }


def _sorted_exits(era: EraSpec, room_id: str, allow_locked: bool):
    room = era.room(room_id)
    rank = {d: i for i, d in enumerate(DIRECTIONS)}
    for ex in sorted(room.exits, key=lambda e: rank[e.direction]):
        if ex.locked and not allow_locked:
            continue
        yield ex


def reachable(era: EraSpec, *, allow_locked: bool = True) -> tuple[str, ...]:
    """Room ids reachable from ``era.start`` in deterministic BFS order."""
    seen = {era.start}
    order = [era.start]
    queue = deque([era.start])
    while queue:
        cur = queue.popleft()
        for ex in _sorted_exits(era, cur, allow_locked):
            if ex.target not in seen:
                seen.add(ex.target)
                order.append(ex.target)
                queue.append(ex.target)
    return tuple(order)


def distances(era: EraSpec, *, allow_locked: bool = True) -> dict[str, int]:
    """Hop count from ``era.start`` to every reachable room."""
    dist = {era.start: 0}
    queue = deque([era.start])
    while queue:
        cur = queue.popleft()
        for ex in _sorted_exits(era, cur, allow_locked):
            if ex.target not in dist:
                dist[ex.target] = dist[cur] + 1
                queue.append(ex.target)
    return dist


def shortest_path(
    era: EraSpec, src: str, dst: str, *, allow_locked: bool = True
) -> tuple[str, ...]:
    """Deterministic shortest room path ``src`` -> ``dst`` (inclusive), or ``()``."""
    era.room(src)
    era.room(dst)
    if src == dst:
        return (src,)
    prev: dict[str, str] = {src: src}
    queue = deque([src])
    while queue:
        cur = queue.popleft()
        for ex in _sorted_exits(era, cur, allow_locked):
            if ex.target in prev:
                continue
            prev[ex.target] = cur
            if ex.target == dst:
                path = [dst]
                while path[-1] != src:
                    path.append(prev[path[-1]])
                return tuple(reversed(path))
            queue.append(ex.target)
    return ()


def check_era(era: EraSpec) -> tuple[Finding, ...]:
    """Semantic checks for one era. Findings are sorted (path, code)."""
    out: list[Finding] = []
    base = f"era.{era.id}"
    index = {r.id: i for i, r in enumerate(era.rooms)}
    open_reach = set(reachable(era, allow_locked=True))
    free_reach = set(reachable(era, allow_locked=False))
    for room in era.rooms:
        rpath = f"{base}.rooms[{index[room.id]}]"
        if room.id not in open_reach:
            out.append(Finding("unreachable-room", rpath, room.id))
        elif room.id not in free_reach:
            out.append(Finding("behind-lock", rpath, room.id, WARNING))
        if not room.exits and room.kind not in TERMINAL_KINDS:
            out.append(Finding("dead-end", rpath, room.id, WARNING))
        for j, ex in enumerate(room.exits):
            back = era.room(ex.target).exit(OPPOSITE[ex.direction])
            if back is None or back.target != room.id:
                out.append(
                    Finding(
                        "one-way-exit",
                        f"{rpath}.exits[{j}]",
                        f"{room.id} -{ex.direction}-> {ex.target} has no return",
                        WARNING,
                    )
                )
    start = era.room(era.start)
    if start.kind in TERMINAL_KINDS:
        out.append(Finding("bad-start-kind", f"{base}.start", start.kind))
    bosses = [r.id for r in era.rooms if r.kind == "boss"]
    if len(bosses) > 1:
        out.append(Finding("multiple-bosses", f"{base}.rooms", ",".join(bosses), WARNING))
    return tuple(sorted(out, key=lambda f: (f.path, f.code)))


def check_campaign(eras: Iterable[EraSpec]) -> tuple[Finding, ...]:
    """Cross-era checks: unique ids, unique ``order`` slots, per-era checks."""
    out: list[Finding] = []
    seen_ids: dict[str, int] = {}
    seen_order: dict[int, str] = {}
    for i, era in enumerate(eras):
        if not isinstance(era, EraSpec):
            raise SchemaError("bad-type", f"eras[{i}]", "expected EraSpec")
        if era.id in seen_ids:
            out.append(Finding("duplicate-era", f"eras[{i}].id", era.id))
        else:
            seen_ids[era.id] = i
        if era.order in seen_order and seen_order[era.order] != era.id:
            out.append(
                Finding(
                    "duplicate-order",
                    f"eras[{i}].order",
                    f"{era.order} already used by {seen_order[era.order]}",
                )
            )
        else:
            seen_order.setdefault(era.order, era.id)
        out.extend(check_era(era))
    return tuple(out)


def errors(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    return tuple(f for f in findings if f.severity == ERROR)


def assert_clean(findings: Iterable[Finding]) -> None:
    """Raise :class:`SchemaError` for the first ``error`` finding, if any."""
    for f in findings:
        if f.severity == ERROR:
            raise SchemaError(f.code, f.path, f.detail)


def summarize(era: EraSpec) -> dict[str, Any]:
    """Stable, JSON-ready summary a later forge/eras pipeline can consume."""
    dist = distances(era)
    findings = check_era(era)
    return {
        "era": era.id,
        "order": era.order,
        "rooms": len(era.rooms),
        "reachable": len(dist),
        "max_hops": max(dist.values()),
        "kinds": {k: sum(1 for r in era.rooms if r.kind == k) for k in sorted({r.kind for r in era.rooms})},
        "errors": sum(1 for f in findings if f.severity == ERROR),
        "warnings": sum(1 for f in findings if f.severity == WARNING),
    }
