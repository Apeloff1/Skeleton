"""Named must lots."""

from __future__ import annotations

from typing import Any


class MustPackError(ValueError):
    pass


MUST = tuple(f"mu_{i:02d}" for i in range(16))


def add(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MUST:
        raise MustPackError(name)
    nxt = dict(state)
    have = list(nxt.get("must_lot") or [])
    have.append(name)
    nxt["must_lot"] = have
    nxt["must"] = int(nxt.get("must", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
