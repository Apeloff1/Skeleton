"""Named lead armings."""

from __future__ import annotations

from typing import Any


class ArmingPackError(ValueError):
    pass


ARMING = tuple(f"ar_{i:02d}" for i in range(12))


def set_arming(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ARMING:
        raise ArmingPackError(name)
    nxt = dict(state)
    nxt["arming"] = name
    nxt["stored_prose"] = 0
    return nxt
