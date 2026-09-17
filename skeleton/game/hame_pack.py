"""Named hames."""

from __future__ import annotations

from typing import Any


class HamePackError(ValueError):
    pass


HAME = tuple(f"hm_{i:02d}" for i in range(12))


def set_hame(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HAME:
        raise HamePackError(name)
    nxt = dict(state)
    have = list(nxt.get("hame") or [])
    have.append(name)
    nxt["hame"] = have
    nxt["stored_prose"] = 0
    return nxt
