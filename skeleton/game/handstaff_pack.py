"""Named handstaffs."""

from __future__ import annotations

from typing import Any


class HandstaffPackError(ValueError):
    pass


STAFF = tuple(f"hs_{i:02d}" for i in range(8))


def set_staff(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STAFF:
        raise HandstaffPackError(name)
    nxt = dict(state)
    nxt["handstaff"] = name
    nxt["stored_prose"] = 0
    return nxt
