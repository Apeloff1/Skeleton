"""Named lime lots."""

from __future__ import annotations

from typing import Any


class LimePackError(ValueError):
    pass


LIME = tuple(f"lm_{i:02d}" for i in range(16))


def add(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LIME:
        raise LimePackError(name)
    nxt = dict(state)
    have = list(nxt.get("lime") or [])
    have.append(name)
    nxt["lime"] = have
    nxt["stored_prose"] = 0
    return nxt
