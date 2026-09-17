"""Named tumblers."""

from __future__ import annotations

from typing import Any


class TumblerPackError(ValueError):
    pass


TUMBLER = tuple(f"tb_{i:02d}" for i in range(12))


def lift(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TUMBLER:
        raise TumblerPackError(name)
    nxt = dict(state)
    nxt["tumbler"] = name
    nxt["lift"] = int(nxt.get("lift", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
