"""Named quenches."""

from __future__ import annotations

from typing import Any


class QuenchPackError(ValueError):
    pass


QUENCH = tuple(f"qn_{i:02d}" for i in range(16))


def dip(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in QUENCH:
        raise QuenchPackError(name)
    nxt = dict(state)
    nxt["quench"] = name
    nxt["heat"] = max(0, int(nxt.get("heat", 0)) - 3)
    nxt["stored_prose"] = 0
    return nxt
