"""Named flour lots."""

from __future__ import annotations

from typing import Any


class FlourPackError(ValueError):
    pass


FLOUR = tuple(f"fl_{i:02d}" for i in range(16))


def grind(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FLOUR:
        raise FlourPackError(name)
    if int(state.get("grain", 0)) < 1:
        raise FlourPackError("grain")
    nxt = dict(state)
    nxt["grain"] = int(nxt.get("grain", 0)) - 1
    have = list(nxt.get("flour") or [])
    have.append(name)
    nxt["flour"] = have
    nxt["stored_prose"] = 0
    return nxt
