"""Named lattices."""

from __future__ import annotations

from typing import Any


class LatticePackError(ValueError):
    pass


LATTICE = tuple(f"lt_{i:02d}" for i in range(20))


def set_lattice(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LATTICE:
        raise LatticePackError(name)
    nxt = dict(node)
    nxt["lattice"] = name
    nxt["stored_prose"] = 0
    return nxt
