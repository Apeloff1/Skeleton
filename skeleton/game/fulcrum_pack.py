"""Named fulcrums."""

from __future__ import annotations

from typing import Any


class FulcrumPackError(ValueError):
    pass


FULC = tuple(f"fu_{i:02d}" for i in range(8))


def set_fulc(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FULC:
        raise FulcrumPackError(name)
    nxt = dict(state)
    nxt["fulcrum"] = name
    nxt["stored_prose"] = 0
    return nxt
