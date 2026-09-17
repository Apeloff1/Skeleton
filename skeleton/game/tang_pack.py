"""Named tangs."""

from __future__ import annotations

from typing import Any


class TangPackError(ValueError):
    pass


TANG = tuple(f"tg_{i:02d}" for i in range(8))


def set_tang(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TANG:
        raise TangPackError(name)
    nxt = dict(state)
    nxt["tang"] = name
    nxt["stored_prose"] = 0
    return nxt
