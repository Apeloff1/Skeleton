"""Named ash lots."""

from __future__ import annotations

from typing import Any


class AshPackError(ValueError):
    pass


ASH = tuple(f"as_{i:02d}" for i in range(12))


def sift(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ASH:
        raise AshPackError(name)
    nxt = dict(state)
    have = list(nxt.get("ash") or [])
    have.append(name)
    nxt["ash"] = have
    nxt["stored_prose"] = 0
    return nxt
