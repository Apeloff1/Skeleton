"""Named flitches."""

from __future__ import annotations

from typing import Any


class FlitchPackError(ValueError):
    pass


FLITCH = tuple(f"fl_{i:02d}" for i in range(12))


def hang(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FLITCH:
        raise FlitchPackError(name)
    nxt = dict(state)
    have = list(nxt.get("flitch") or [])
    have.append(name)
    nxt["flitch"] = have
    nxt["stored_prose"] = 0
    return nxt
