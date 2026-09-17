"""Named vows."""

from __future__ import annotations

from typing import Any


class VowPackError(ValueError):
    pass


VOW = tuple(f"vw_{i:02d}" for i in range(16))


def take(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in VOW:
        raise VowPackError(name)
    nxt = dict(state)
    have = list(nxt.get("vow") or [])
    if name not in have:
        have.append(name)
    nxt["vow"] = have
    nxt["stored_prose"] = 0
    return nxt
