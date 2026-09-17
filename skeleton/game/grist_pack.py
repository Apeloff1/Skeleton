"""Named grist lots."""

from __future__ import annotations

from typing import Any


class GristPackError(ValueError):
    pass


GRIST = tuple(f"gr_{i:02d}" for i in range(12))


def mill(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GRIST:
        raise GristPackError(name)
    nxt = dict(state)
    have = list(nxt.get("grist") or [])
    have.append(name)
    nxt["grist"] = have
    nxt["stored_prose"] = 0
    return nxt
