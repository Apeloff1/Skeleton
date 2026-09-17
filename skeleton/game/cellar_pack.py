"""Named cellars."""

from __future__ import annotations

from typing import Any


class CellarPackError(ValueError):
    pass


CELLAR = tuple(f"cl_{i:02d}" for i in range(8))


def set_cellar(node: dict[str, Any], name: str, cool: int) -> dict[str, Any]:
    if name not in CELLAR:
        raise CellarPackError(name)
    nxt = dict(node)
    nxt["cellar"] = name
    nxt["cool"] = max(0, int(cool))
    nxt["stored_prose"] = 0
    return nxt
