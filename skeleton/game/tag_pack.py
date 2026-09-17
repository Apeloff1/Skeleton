"""Named graffiti tags. Pointer only."""

from __future__ import annotations

from typing import Any


class TagPackError(ValueError):
    pass


TAGS = tuple(f"tg_{i:02d}" for i in range(24))


def mark(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TAGS:
        raise TagPackError(name)
    nxt = dict(node)
    tags = list(nxt.get("tag") or [])
    if name not in tags:
        tags.append(name)
    nxt["tag"] = tags
    nxt["stored_prose"] = 0
    return nxt
