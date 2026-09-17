"""Named sieves."""

from __future__ import annotations

from typing import Any


class SievePackError(ValueError):
    pass


SIEVE = tuple(f"sv_{i:02d}" for i in range(16))


def shake(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SIEVE:
        raise SievePackError(name)
    nxt = dict(state)
    nxt["sieve"] = name
    nxt["fine"] = int(nxt.get("fine", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
