"""Named rivets."""

from __future__ import annotations

from typing import Any


class RivetPackError(ValueError):
    pass


RIVET = tuple(f"rv_{i:02d}" for i in range(28))


def drive(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in RIVET:
        raise RivetPackError(name)
    nxt = dict(state)
    have = list(nxt.get("rivet") or [])
    have.append(name)
    nxt["rivet"] = have
    nxt["stored_prose"] = 0
    return nxt
