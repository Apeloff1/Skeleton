"""Named lantern globes."""

from __future__ import annotations

from typing import Any


class GlobePackError(ValueError):
    pass


GLOBE = tuple(f"gb_{i:02d}" for i in range(12))


def set_globe(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GLOBE:
        raise GlobePackError(name)
    nxt = dict(node)
    nxt["globe"] = name
    nxt["stored_prose"] = 0
    return nxt
