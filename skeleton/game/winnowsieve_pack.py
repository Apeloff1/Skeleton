"""Named winnow sieves."""

from __future__ import annotations

from typing import Any


class WinnowsievePackError(ValueError):
    pass


SIEVE = tuple(f"ws_{i:02d}" for i in range(8))


def shake(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SIEVE:
        raise WinnowsievePackError(name)
    nxt = dict(state)
    nxt["winnowsieve"] = name
    nxt["grain"] = int(nxt.get("grain", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
