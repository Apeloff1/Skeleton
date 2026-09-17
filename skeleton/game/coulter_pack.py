"""Named coulters."""

from __future__ import annotations

from typing import Any


class CoulterPackError(ValueError):
    pass


COULTER = tuple(f"ct_{i:02d}" for i in range(8))


def set_coulter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COULTER:
        raise CoulterPackError(name)
    nxt = dict(state)
    nxt["coulter"] = name
    nxt["stored_prose"] = 0
    return nxt
