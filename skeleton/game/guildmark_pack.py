"""Named guild marks."""

from __future__ import annotations

from typing import Any


class GuildmarkPackError(ValueError):
    pass


MARK = tuple(f"gm_{i:02d}" for i in range(12))


def stamp(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MARK:
        raise GuildmarkPackError(name)
    nxt = dict(state)
    nxt["guildmark"] = name
    nxt["stamped"] = 1
    nxt["stored_prose"] = 0
    return nxt
