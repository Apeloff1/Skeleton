"""Named strakes."""

from __future__ import annotations

from typing import Any


class StrakePackError(ValueError):
    pass


STRAKE = tuple(f"sk_{i:02d}" for i in range(16))


def set_strake(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STRAKE:
        raise StrakePackError(name)
    nxt = dict(node)
    have = list(nxt.get("strake") or [])
    have.append(name)
    nxt["strake"] = have
    nxt["stored_prose"] = 0
    return nxt
