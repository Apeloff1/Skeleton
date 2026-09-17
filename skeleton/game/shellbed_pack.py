"""Named shell beds."""

from __future__ import annotations

from typing import Any


class ShellbedPackError(ValueError):
    pass


BED = tuple(f"sb_{i:02d}" for i in range(8))


def set_bed(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BED:
        raise ShellbedPackError(name)
    nxt = dict(node)
    nxt["shellbed"] = name
    nxt["stored_prose"] = 0
    return nxt
