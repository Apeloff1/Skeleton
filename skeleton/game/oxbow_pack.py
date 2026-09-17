"""Named oxbows."""

from __future__ import annotations

from typing import Any


class OxbowPackError(ValueError):
    pass


OXBOW = tuple(f"ox_{i:02d}" for i in range(12))


def set_bow(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in OXBOW:
        raise OxbowPackError(name)
    nxt = dict(state)
    have = list(nxt.get("oxbow") or [])
    have.append(name)
    nxt["oxbow"] = have
    nxt["stored_prose"] = 0
    return nxt
