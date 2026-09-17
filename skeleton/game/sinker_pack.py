"""Named sinkers."""

from __future__ import annotations

from typing import Any


class SinkerPackError(ValueError):
    pass


SINK = tuple(f"sk_{i:02d}" for i in range(16))


def set_sink(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SINK:
        raise SinkerPackError(name)
    nxt = dict(state)
    have = list(nxt.get("sinker") or [])
    have.append(name)
    nxt["sinker"] = have
    nxt["stored_prose"] = 0
    return nxt
