"""Named faggots."""

from __future__ import annotations

from typing import Any


class FaggotPackError(ValueError):
    pass


FAGGOT = tuple(f"fg_{i:02d}" for i in range(16))


def bind(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FAGGOT:
        raise FaggotPackError(name)
    nxt = dict(state)
    have = list(nxt.get("faggot") or [])
    have.append(name)
    nxt["faggot"] = have
    nxt["stored_prose"] = 0
    return nxt
