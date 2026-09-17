"""Named charts. Pointer only."""

from __future__ import annotations

from typing import Any


class ChartPackError(ValueError):
    pass


CHART = tuple(f"ch_{i:02d}" for i in range(20))


def note(state: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in CHART:
        raise ChartPackError(name)
    if not digest:
        raise ChartPackError("digest")
    nxt = dict(state)
    cur = dict(nxt.get("chart") or {})
    cur[name] = digest
    nxt["chart"] = cur
    nxt["stored_prose"] = 0
    return nxt
