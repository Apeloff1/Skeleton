"""Named fullers."""

from __future__ import annotations

from typing import Any


class FullerPackError(ValueError):
    pass


FULLER = tuple(f"fu_{i:02d}" for i in range(12))


def groove(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FULLER:
        raise FullerPackError(name)
    nxt = dict(state)
    nxt["fuller"] = name
    nxt["stored_prose"] = 0
    return nxt
