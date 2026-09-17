"""Named bolts."""

from __future__ import annotations

from typing import Any


class BoltPackError(ValueError):
    pass


BOLT = tuple(f"bt_{i:02d}" for i in range(28))


def drive(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BOLT:
        raise BoltPackError(name)
    nxt = dict(state)
    have = list(nxt.get("bolt") or [])
    have.append(name)
    nxt["bolt"] = have
    nxt["stored_prose"] = 0
    return nxt
