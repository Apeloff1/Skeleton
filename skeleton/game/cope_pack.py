"""Named copes."""

from __future__ import annotations

from typing import Any


class CopePackError(ValueError):
    pass


COPE = tuple(f"cp_{i:02d}" for i in range(12))


def set_cope(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COPE:
        raise CopePackError(name)
    nxt = dict(state)
    nxt["cope"] = name
    nxt["stored_prose"] = 0
    return nxt
