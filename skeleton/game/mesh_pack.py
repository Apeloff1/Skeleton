"""Named meshes."""

from __future__ import annotations

from typing import Any


class MeshPackError(ValueError):
    pass


MESH = tuple(f"mh_{i:02d}" for i in range(12))


def set_mesh(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in MESH:
        raise MeshPackError(name)
    nxt = dict(state)
    nxt["mesh"] = name
    nxt["size"] = max(1, int(n))
    nxt["stored_prose"] = 0
    return nxt
