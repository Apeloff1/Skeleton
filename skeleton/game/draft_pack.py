"""Named drafts."""

from __future__ import annotations

from typing import Any


class DraftPackError(ValueError):
    pass


DRAFT = tuple(f"dr_{i:02d}" for i in range(20))


def blow(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DRAFT:
        raise DraftPackError(name)
    nxt = dict(node)
    nxt["draft"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + ((DRAFT.index(name) % 5) - 2)))
    nxt["stored_prose"] = 0
    return nxt
