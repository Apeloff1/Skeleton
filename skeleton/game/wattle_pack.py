"""Named wattles."""

from __future__ import annotations

from typing import Any


class WattlePackError(ValueError):
    pass


WATTLE = tuple(f"wt_{i:02d}" for i in range(12))


def weave(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WATTLE:
        raise WattlePackError(name)
    nxt = dict(node)
    nxt["wattle"] = name
    nxt["stored_prose"] = 0
    return nxt
