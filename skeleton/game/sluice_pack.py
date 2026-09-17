"""Named sluices."""

from __future__ import annotations

from typing import Any


class SluicePackError(ValueError):
    pass


SLUICE = tuple(f"sl_{i:02d}" for i in range(12))


def set_gate(node: dict[str, Any], name: str, open_: int) -> dict[str, Any]:
    if name not in SLUICE:
        raise SluicePackError(name)
    nxt = dict(node)
    nxt["sluice"] = name
    nxt["open"] = int(bool(open_))
    nxt["stored_prose"] = 0
    return nxt
