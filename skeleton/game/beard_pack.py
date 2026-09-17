"""Named beards."""

from __future__ import annotations

from typing import Any


class BeardPackError(ValueError):
    pass


BEARD = tuple(f"bd_{i:02d}" for i in range(8))


def set_beard(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BEARD:
        raise BeardPackError(name)
    nxt = dict(state)
    nxt["beard"] = name
    nxt["cut"] = int(nxt.get("cut", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
