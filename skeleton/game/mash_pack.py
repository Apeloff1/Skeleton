"""Named mashes."""

from __future__ import annotations

from typing import Any


class MashPackError(ValueError):
    pass


MASH = tuple(f"ms_{i:02d}" for i in range(8))


def set_mash(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MASH:
        raise MashPackError(name)
    nxt = dict(state)
    nxt["mash"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
