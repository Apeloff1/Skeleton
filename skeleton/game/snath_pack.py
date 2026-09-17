"""Named snaths."""

from __future__ import annotations

from typing import Any


class SnathPackError(ValueError):
    pass


SNATH = tuple(f"sn_{i:02d}" for i in range(8))


def set_snath(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SNATH:
        raise SnathPackError(name)
    nxt = dict(state)
    nxt["snath"] = name
    nxt["stored_prose"] = 0
    return nxt
