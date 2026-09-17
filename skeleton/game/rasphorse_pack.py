"""Named horse rasps."""

from __future__ import annotations

from typing import Any


class RasphorsePackError(ValueError):
    pass


RASP = tuple(f"rh_{i:02d}" for i in range(12))


def rasp(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RASP:
        raise RasphorsePackError(name)
    nxt = dict(state)
    nxt["rasphorse"] = name
    nxt["trim"] = int(nxt.get("trim", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
