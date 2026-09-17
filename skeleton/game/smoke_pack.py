"""Named smoke pots."""

from __future__ import annotations

from typing import Any


class SmokePackError(ValueError):
    pass


SMOKE = tuple(f"sk_{i:02d}" for i in range(12))


def puff(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SMOKE:
        raise SmokePackError(name)
    nxt = dict(state)
    nxt["smoke"] = name
    nxt["alert"] = max(0, int(nxt.get("alert", 0)) - 1)
    nxt["stored_prose"] = 0
    return nxt
