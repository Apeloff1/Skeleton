"""Named winnow baskets."""

from __future__ import annotations

from typing import Any


class WinnowbasketPackError(ValueError):
    pass


BASKET = tuple(f"wb_{i:02d}" for i in range(8))


def set_basket(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BASKET:
        raise WinnowbasketPackError(name)
    nxt = dict(state)
    nxt["winnowbasket"] = name
    nxt["stored_prose"] = 0
    return nxt
