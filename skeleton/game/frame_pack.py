"""Named frames."""

from __future__ import annotations

from typing import Any


class FramePackError(ValueError):
    pass


FRAME = tuple(f"fr_{i:02d}" for i in range(20))


def hang(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FRAME:
        raise FramePackError(name)
    nxt = dict(node)
    have = list(nxt.get("frame") or [])
    if name not in have:
        have.append(name)
    nxt["frame"] = have
    nxt["stored_prose"] = 0
    return nxt
