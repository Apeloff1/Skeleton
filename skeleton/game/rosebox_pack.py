"""Named rose boxes."""

from __future__ import annotations

from typing import Any


class RoseboxPackError(ValueError):
    pass


ROSE = tuple(f"rb_{i:02d}" for i in range(8))


def set_rose(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ROSE:
        raise RoseboxPackError(name)
    nxt = dict(node)
    nxt["rosebox"] = name
    nxt["stored_prose"] = 0
    return nxt
