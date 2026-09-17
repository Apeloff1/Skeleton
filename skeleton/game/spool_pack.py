"""Named wire spools."""

from __future__ import annotations

from typing import Any


class SpoolPackError(ValueError):
    pass


SPOOL = tuple(f"sp_{i:02d}" for i in range(24))


def pull(state: dict[str, Any], name: str, n: int = 1) -> dict[str, Any]:
    if name not in SPOOL:
        raise SpoolPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("spool") or {})
    left = int(cur.get(name, 4 + (SPOOL.index(name) % 4)))
    if left < n:
        raise SpoolPackError("empty")
    cur[name] = left - int(n)
    nxt["spool"] = cur
    nxt["stored_prose"] = 0
    return nxt
