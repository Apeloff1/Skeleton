"""Named structural beams."""

from __future__ import annotations

from typing import Any


class BeamPackError(ValueError):
    pass


BEAM = tuple(f"bm_{i:02d}" for i in range(20))


def stress(node: dict[str, Any], name: str, load: int) -> dict[str, Any]:
    if name not in BEAM:
        raise BeamPackError(name)
    nxt = dict(node)
    nxt["beam"] = name
    nxt["stress"] = max(0, min(16, int(load) + (BEAM.index(name) % 4)))
    nxt["stored_prose"] = 0
    return nxt
