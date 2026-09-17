"""Named channels."""

from __future__ import annotations

from typing import Any


class ChannelPackError(ValueError):
    pass


CHAN = tuple(f"ch_{i:02d}" for i in range(16))


def cut(node: dict[str, Any], name: str, dest: str) -> dict[str, Any]:
    if name not in CHAN:
        raise ChannelPackError(name)
    nxt = dict(node)
    nxt["channel"] = name
    nxt["dest"] = dest
    nxt["stored_prose"] = 0
    return nxt
