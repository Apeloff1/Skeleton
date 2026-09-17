"""Named stirrups."""

from __future__ import annotations

from typing import Any


class StirrupPackError(ValueError):
    pass


STIRRUP = tuple(f"sr_{i:02d}" for i in range(12))


def set_stirrup(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STIRRUP:
        raise StirrupPackError(name)
    nxt = dict(state)
    have = list(nxt.get("stirrup") or [])
    have.append(name)
    nxt["stirrup"] = have
    nxt["stored_prose"] = 0
    return nxt
