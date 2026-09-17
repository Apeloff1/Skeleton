"""Named iron blooms."""

from __future__ import annotations

from typing import Any


class BloomPackError(ValueError):
    pass


BLOOM = tuple(f"bm_{i:02d}" for i in range(16))


def draw(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BLOOM:
        raise BloomPackError(name)
    nxt = dict(state)
    have = list(nxt.get("bloom") or [])
    have.append(name)
    nxt["bloom"] = have
    nxt["stored_prose"] = 0
    return nxt
