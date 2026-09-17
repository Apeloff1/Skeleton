"""Named scythe heels."""

from __future__ import annotations

from typing import Any


class ScytheheelPackError(ValueError):
    pass


HEEL = tuple(f"hl_{i:02d}" for i in range(8))


def set_heel(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HEEL:
        raise ScytheheelPackError(name)
    nxt = dict(state)
    nxt["scytheheel"] = name
    nxt["stored_prose"] = 0
    return nxt
