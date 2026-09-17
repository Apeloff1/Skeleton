"""Named coils."""

from __future__ import annotations

from typing import Any


class CoilPackError(ValueError):
    pass


COIL = tuple(f"cl_{i:02d}" for i in range(16))


def wind(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COIL:
        raise CoilPackError(name)
    nxt = dict(state)
    have = list(nxt.get("coil") or [])
    have.append(name)
    nxt["coil"] = have
    nxt["stored_prose"] = 0
    return nxt
