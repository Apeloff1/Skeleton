"""Named cords / lines."""

from __future__ import annotations

from typing import Any


class CordPackError(ValueError):
    pass


CORD = tuple(f"cd_{i:02d}" for i in range(24))


def tie(state: dict[str, Any], name: str, a: str, b: str) -> dict[str, Any]:
    if name not in CORD:
        raise CordPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("cord") or {})
    cur[name] = (a, b)
    nxt["cord"] = cur
    nxt["stored_prose"] = 0
    return nxt
