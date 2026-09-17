"""Named fyke nets."""

from __future__ import annotations

from typing import Any


class FykePackError(ValueError):
    pass


FYKE = tuple(f"fk_{i:02d}" for i in range(8))


def set_fyke(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FYKE:
        raise FykePackError(name)
    nxt = dict(node)
    nxt["fyke"] = name
    nxt["stored_prose"] = 0
    return nxt
