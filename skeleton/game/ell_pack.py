"""Named ells."""

from __future__ import annotations

from typing import Any


class EllPackError(ValueError):
    pass


ELL = tuple(f"el_{i:02d}" for i in range(8))


def measure(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in ELL:
        raise EllPackError(name)
    nxt = dict(state)
    nxt["ell"] = name
    nxt["len"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
