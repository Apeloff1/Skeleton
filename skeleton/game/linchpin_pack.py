"""Named linchpins."""

from __future__ import annotations

from typing import Any


class LinchpinPackError(ValueError):
    pass


PIN = tuple(f"lp_{i:02d}" for i in range(12))


def set_pin(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PIN:
        raise LinchpinPackError(name)
    nxt = dict(state)
    nxt["linchpin"] = name
    nxt["locked"] = 1
    nxt["stored_prose"] = 0
    return nxt
