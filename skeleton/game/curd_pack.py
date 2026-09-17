"""Named curds."""

from __future__ import annotations

from typing import Any


class CurdPackError(ValueError):
    pass


CURD = tuple(f"cd_{i:02d}" for i in range(16))


def set_curd(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CURD:
        raise CurdPackError(name)
    nxt = dict(state)
    have = list(nxt.get("curd") or [])
    have.append(name)
    nxt["curd"] = have
    nxt["stored_prose"] = 0
    return nxt
