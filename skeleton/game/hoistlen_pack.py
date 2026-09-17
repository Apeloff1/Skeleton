"""Named hoist lengths."""

from __future__ import annotations

from typing import Any


class HoistlenPackError(ValueError):
    pass


HOIST = tuple(f"hs_{i:02d}" for i in range(12))


def set_hoist(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in HOIST:
        raise HoistlenPackError(name)
    nxt = dict(state)
    nxt["hoistlen"] = name
    nxt["hoist"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
