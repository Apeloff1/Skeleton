"""Named wardships."""

from __future__ import annotations

from typing import Any


class WardshipPackError(ValueError):
    pass


WARD = tuple(f"wd_{i:02d}" for i in range(8))


def take(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WARD:
        raise WardshipPackError(name)
    nxt = dict(state)
    nxt["wardship"] = name
    nxt["held"] = 1
    nxt["stored_prose"] = 0
    return nxt
