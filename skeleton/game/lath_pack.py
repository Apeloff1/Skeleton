"""Named laths."""

from __future__ import annotations

from typing import Any


class LathPackError(ValueError):
    pass


LATH = tuple(f"lt_{i:02d}" for i in range(16))


def nail(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LATH:
        raise LathPackError(name)
    nxt = dict(node)
    have = list(nxt.get("lath") or [])
    have.append(name)
    nxt["lath"] = have
    nxt["stored_prose"] = 0
    return nxt
