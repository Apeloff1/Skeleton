"""Named felloes."""

from __future__ import annotations

from typing import Any


class FelloePackError(ValueError):
    pass


FELLOE = tuple(f"fe_{i:02d}" for i in range(16))


def set_felloe(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FELLOE:
        raise FelloePackError(name)
    nxt = dict(state)
    have = list(nxt.get("felloe") or [])
    have.append(name)
    nxt["felloe"] = have
    nxt["stored_prose"] = 0
    return nxt
