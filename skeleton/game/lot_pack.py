"""Named stock lots."""

from __future__ import annotations

from typing import Any


class LotPackError(ValueError):
    pass


LOT = tuple(f"lt_{i:02d}" for i in range(28))


def add(state: dict[str, Any], name: str, n: int = 1) -> dict[str, Any]:
    if name not in LOT:
        raise LotPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("lot") or {})
    cur[name] = int(cur.get(name, 0)) + int(n)
    nxt["lot"] = cur
    nxt["stored_prose"] = 0
    return nxt
