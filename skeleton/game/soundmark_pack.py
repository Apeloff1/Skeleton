"""Named sound marks."""

from __future__ import annotations

from typing import Any


class SoundmarkPackError(ValueError):
    pass


MARK = tuple(f"mk_{i:02d}" for i in range(16))


def read(state: dict[str, Any], name: str, fath: int) -> dict[str, Any]:
    if name not in MARK:
        raise SoundmarkPackError(name)
    nxt = dict(state)
    nxt["soundmark"] = name
    nxt["fath"] = max(0, int(fath))
    nxt["stored_prose"] = 0
    return nxt
