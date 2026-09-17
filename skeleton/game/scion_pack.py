"""Named scions."""

from __future__ import annotations

from typing import Any


class ScionPackError(ValueError):
    pass


SCION = tuple(f"sc_{i:02d}" for i in range(12))


def set_scion(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SCION:
        raise ScionPackError(name)
    nxt = dict(state)
    nxt["scion"] = name
    nxt["stored_prose"] = 0
    return nxt
