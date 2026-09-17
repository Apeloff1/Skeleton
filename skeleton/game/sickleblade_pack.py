"""Named sickle blades."""

from __future__ import annotations

from typing import Any


class SicklebladePackError(ValueError):
    pass


BLADE = tuple(f"sb_{i:02d}" for i in range(12))


def set_blade(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BLADE:
        raise SicklebladePackError(name)
    nxt = dict(state)
    nxt["sickleblade"] = name
    nxt["cut"] = int(nxt.get("cut", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
