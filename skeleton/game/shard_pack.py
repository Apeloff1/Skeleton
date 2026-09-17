"""Named shards."""

from __future__ import annotations

from typing import Any


class ShardPackError(ValueError):
    pass


SHARD = tuple(f"sd_{i:02d}" for i in range(24))


def cut(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SHARD:
        raise ShardPackError(name)
    nxt = dict(state)
    have = list(nxt.get("shard") or [])
    have.append(name)
    nxt["shard"] = have
    nxt["hp"] = max(0, int(nxt.get("hp", 40)) - (1 + (SHARD.index(name) % 2)))
    nxt["stored_prose"] = 0
    return nxt
