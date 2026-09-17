"""Named sutures."""

from __future__ import annotations

from typing import Any


class SuturePackError(ValueError):
    pass


SUTURE = tuple(f"su_{i:02d}" for i in range(20))


def close(state: dict[str, Any], name: str, site: str) -> dict[str, Any]:
    if name not in SUTURE:
        raise SuturePackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("suture") or {})
    cur[name] = site
    nxt["suture"] = cur
    nxt["hp"] = min(40, int(nxt.get("hp", 40)) + 1)
    nxt["stored_prose"] = 0
    return nxt
