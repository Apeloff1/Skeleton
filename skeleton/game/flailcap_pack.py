"""Named flail caps."""

from __future__ import annotations

from typing import Any


class FlailcapPackError(ValueError):
    pass


CAP = tuple(f"fc_{i:02d}" for i in range(8))


def set_cap(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CAP:
        raise FlailcapPackError(name)
    nxt = dict(state)
    nxt["flailcap"] = name
    nxt["stored_prose"] = 0
    return nxt
