"""Named worts."""

from __future__ import annotations

from typing import Any


class WortPackError(ValueError):
    pass


WORT = tuple(f"wt_{i:02d}" for i in range(8))


def set_wort(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WORT:
        raise WortPackError(name)
    nxt = dict(state)
    nxt["wort"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
