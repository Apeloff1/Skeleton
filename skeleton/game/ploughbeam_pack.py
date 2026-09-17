"""Named plough beams."""

from __future__ import annotations

from typing import Any


class PloughbeamPackError(ValueError):
    pass


BEAM = tuple(f"pb_{i:02d}" for i in range(8))


def set_beam(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BEAM:
        raise PloughbeamPackError(name)
    nxt = dict(state)
    nxt["ploughbeam"] = name
    nxt["stored_prose"] = 0
    return nxt
