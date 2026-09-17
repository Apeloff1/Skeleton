"""Named soap cakes."""

from __future__ import annotations

from typing import Any


class CakePackError(ValueError):
    pass


CAKE = tuple(f"ck_{i:02d}" for i in range(16))


def cut(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CAKE:
        raise CakePackError(name)
    nxt = dict(state)
    have = list(nxt.get("cake") or [])
    have.append(name)
    nxt["cake"] = have
    nxt["stored_prose"] = 0
    return nxt
