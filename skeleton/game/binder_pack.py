"""Named binders."""

from __future__ import annotations

from typing import Any


class BinderPackError(ValueError):
    pass


BINDER = tuple(f"bd_{i:02d}" for i in range(12))


def bind(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BINDER:
        raise BinderPackError(name)
    nxt = dict(state)
    nxt["binder"] = name
    nxt["tight"] = 1
    nxt["stored_prose"] = 0
    return nxt
