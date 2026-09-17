"""Named garboards."""

from __future__ import annotations

from typing import Any


class GarboardPackError(ValueError):
    pass


GARBOARD = tuple(f"gb_{i:02d}" for i in range(8))


def set_garboard(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GARBOARD:
        raise GarboardPackError(name)
    nxt = dict(node)
    nxt["garboard"] = name
    nxt["stored_prose"] = 0
    return nxt
