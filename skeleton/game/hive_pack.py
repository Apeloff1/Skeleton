"""Named hives."""

from __future__ import annotations

from typing import Any


class HivePackError(ValueError):
    pass


HIVE = tuple(f"hv_{i:02d}" for i in range(16))


def set_hive(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HIVE:
        raise HivePackError(name)
    nxt = dict(node)
    nxt["hive"] = name
    nxt["stored_prose"] = 0
    return nxt
