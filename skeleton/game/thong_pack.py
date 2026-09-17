"""Named thongs."""

from __future__ import annotations

from typing import Any


class ThongPackError(ValueError):
    pass


THONG = tuple(f"th_{i:02d}" for i in range(8))


def set_thong(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in THONG:
        raise ThongPackError(name)
    nxt = dict(state)
    nxt["thong"] = name
    nxt["stored_prose"] = 0
    return nxt
