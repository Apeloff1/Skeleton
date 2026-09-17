"""Named oakum lots."""

from __future__ import annotations

from typing import Any


class OakumPackError(ValueError):
    pass


OAKUM = tuple(f"ok_{i:02d}" for i in range(16))


def take(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in OAKUM:
        raise OakumPackError(name)
    nxt = dict(state)
    have = list(nxt.get("oakum") or [])
    have.append(name)
    nxt["oakum"] = have
    nxt["stored_prose"] = 0
    return nxt
