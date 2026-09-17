"""Named ore lots."""

from __future__ import annotations

from typing import Any


class OrePackError(ValueError):
    pass


ORE = tuple(f"or_{i:02d}" for i in range(28))


def dig(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ORE:
        raise OrePackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("ore") or {})
    cur[name] = int(cur.get(name, 0)) + 1
    nxt["ore"] = cur
    nxt["stored_prose"] = 0
    return nxt
