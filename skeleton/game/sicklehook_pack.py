"""Named sickle hooks."""

from __future__ import annotations

from typing import Any


class SicklehookPackError(ValueError):
    pass


HOOK = tuple(f"sk_{i:02d}" for i in range(12))


def set_hook(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HOOK:
        raise SicklehookPackError(name)
    nxt = dict(state)
    nxt["sicklehook"] = name
    nxt["stored_prose"] = 0
    return nxt
