"""Named uniforms."""

from __future__ import annotations

from typing import Any


class UniformPackError(ValueError):
    pass


UNIF = tuple(f"uf_{i:02d}" for i in range(16))


def don(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in UNIF:
        raise UniformPackError(name)
    nxt = dict(state)
    nxt["uniform"] = name
    nxt["stored_prose"] = 0
    return nxt
