"""Named prickings."""

from __future__ import annotations

from typing import Any


class PrickingPackError(ValueError):
    pass


PRICK = tuple(f"pk_{i:02d}" for i in range(12))


def prick(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PRICK:
        raise PrickingPackError(name)
    nxt = dict(state)
    nxt["pricking"] = name
    nxt["ruled"] = 1
    nxt["stored_prose"] = 0
    return nxt
