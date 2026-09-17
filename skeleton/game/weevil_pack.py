"""Named weevil marks."""

from __future__ import annotations

from typing import Any


class WeevilPackError(ValueError):
    pass


WEEVIL = tuple(f"wv_{i:02d}" for i in range(8))


def mark(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WEEVIL:
        raise WeevilPackError(name)
    nxt = dict(state)
    nxt["weevil"] = name
    nxt["loss"] = int(nxt.get("loss", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
