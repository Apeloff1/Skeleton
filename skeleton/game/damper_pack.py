"""Named dampers."""

from __future__ import annotations

from typing import Any


class DamperPackError(ValueError):
    pass


DAMP = tuple(f"dp_{i:02d}" for i in range(16))


def set_damp(node: dict[str, Any], name: str, open_: int) -> dict[str, Any]:
    if name not in DAMP:
        raise DamperPackError(name)
    nxt = dict(node)
    nxt["damper"] = name
    nxt["open"] = int(bool(open_))
    nxt["stored_prose"] = 0
    return nxt
