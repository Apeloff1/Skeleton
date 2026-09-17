"""Named ethers."""

from __future__ import annotations

from typing import Any


class EtherPackError(ValueError):
    pass


ETHER = tuple(f"et_{i:02d}" for i in range(12))


def weave(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ETHER:
        raise EtherPackError(name)
    nxt = dict(state)
    nxt["ether"] = name
    nxt["stored_prose"] = 0
    return nxt
