"""Named witnesses."""

from __future__ import annotations

from typing import Any


class WitnessPackError(ValueError):
    pass


WIT = tuple(f"wt_{i:02d}" for i in range(12))


def sign(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WIT:
        raise WitnessPackError(name)
    nxt = dict(state)
    have = list(nxt.get("witness") or [])
    have.append(name)
    nxt["witness"] = have
    nxt["stored_prose"] = 0
    return nxt
