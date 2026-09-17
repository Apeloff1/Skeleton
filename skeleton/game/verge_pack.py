"""Named verges."""

from __future__ import annotations

from typing import Any


class VergePackError(ValueError):
    pass


VERGE = tuple(f"vg_{i:02d}" for i in range(12))


def set_verge(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in VERGE:
        raise VergePackError(name)
    nxt = dict(state)
    nxt["verge"] = name
    nxt["stored_prose"] = 0
    return nxt
