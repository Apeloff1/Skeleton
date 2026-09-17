"""Named traces."""

from __future__ import annotations

from typing import Any


class TracesetPackError(ValueError):
    pass


TRACE = tuple(f"tr_{i:02d}" for i in range(12))


def set_trace(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TRACE:
        raise TracesetPackError(name)
    nxt = dict(state)
    have = list(nxt.get("trace") or [])
    have.append(name)
    nxt["trace"] = have
    nxt["stored_prose"] = 0
    return nxt
