"""Named combs."""

from __future__ import annotations

from typing import Any


class CombPackError(ValueError):
    pass


COMB = tuple(f"cb_{i:02d}" for i in range(20))


def pull(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COMB:
        raise CombPackError(name)
    nxt = dict(state)
    have = list(nxt.get("comb") or [])
    have.append(name)
    nxt["comb"] = have
    nxt["stored_prose"] = 0
    return nxt
