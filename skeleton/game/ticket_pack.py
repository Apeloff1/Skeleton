"""Named ticket stubs."""

from __future__ import annotations

from typing import Any


class TicketPackError(ValueError):
    pass


TICKET = tuple(f"tk_{i:02d}" for i in range(20))


def tear(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TICKET:
        raise TicketPackError(name)
    nxt = dict(state)
    have = list(nxt.get("ticket") or [])
    if name not in have:
        have.append(name)
    nxt["ticket"] = have
    nxt["stored_prose"] = 0
    return nxt
