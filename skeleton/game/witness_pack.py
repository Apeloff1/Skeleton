"""Named witnesses."""

from __future__ import annotations

from typing import Any


class WitnessPackError(ValueError):
    pass


WIT = tuple(f"wi_{i:02d}" for i in range(16))


def see(state: dict[str, Any], name: str, verb: str) -> dict[str, Any]:
    if name not in WIT:
        raise WitnessPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("saw") or {})
    cur[name] = verb
    nxt["saw"] = cur
    nxt["stored_prose"] = 0
    return nxt
