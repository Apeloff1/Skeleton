"""Named world flags."""

from __future__ import annotations

from typing import Any


class FlagPackError(ValueError):
    pass


FLAGS = tuple(f"fg_{i:02d}" for i in range(24))


def set_flag(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FLAGS:
        raise FlagPackError(name)
    nxt = dict(state)
    flags = dict(nxt.get("flag") or {})
    flags[name] = 1
    nxt["flag"] = flags
    nxt["stored_prose"] = 0
    return nxt
