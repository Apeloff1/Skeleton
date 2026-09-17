"""Named memorials."""

from __future__ import annotations

from typing import Any


class MemorialPackError(ValueError):
    pass


MEM = tuple(f"mm_{i:02d}" for i in range(12))


def record(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MEM:
        raise MemorialPackError(name)
    nxt = dict(state)
    nxt["memorial"] = name
    nxt["kept"] = 1
    nxt["stored_prose"] = 0
    return nxt
