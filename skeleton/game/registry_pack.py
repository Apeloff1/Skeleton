"""Named registries."""

from __future__ import annotations

from typing import Any


class RegistryPackError(ValueError):
    pass


REG = tuple(f"rg_{i:02d}" for i in range(8))


def set_reg(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in REG:
        raise RegistryPackError(name)
    nxt = dict(node)
    nxt["registry"] = name
    nxt["stored_prose"] = 0
    return nxt
