"""Named piers."""

from __future__ import annotations

from typing import Any


class PierPackError(ValueError):
    pass


PIER = tuple(f"pr_{i:02d}" for i in range(16))


def set_pier(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PIER:
        raise PierPackError(name)
    nxt = dict(node)
    nxt["pier"] = name
    nxt["stored_prose"] = 0
    return nxt
