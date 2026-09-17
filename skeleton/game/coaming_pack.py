"""Named coamings."""

from __future__ import annotations

from typing import Any


class CoamingPackError(ValueError):
    pass


COAMING = tuple(f"cm_{i:02d}" for i in range(12))


def set_coaming(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COAMING:
        raise CoamingPackError(name)
    nxt = dict(node)
    nxt["coaming"] = name
    nxt["stored_prose"] = 0
    return nxt
