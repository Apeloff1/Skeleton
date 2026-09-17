"""Named hunter roles."""

from __future__ import annotations

from typing import Any


class RolePackError(ValueError):
    pass


ROLES = (
    "scout", "chaser", "blocker", "sentry", "baiter", "warden",
    "runner", "sleeper", "forger", "clerk", "doctor", "clipper",
    "herald", "rat", "monk", "ref",
)


def step(agent: dict[str, Any], player: str, arrows: dict[str, str | None], t: int) -> dict[str, Any]:
    role = str(agent.get("role") or "")
    if role not in ROLES:
        raise RolePackError(role)
    nxt = dict(agent)
    i = ROLES.index(role)
    room = str(nxt.get("room") or "")
    nxt_room = arrows.get(room)
    if i % 2 == 0 and nxt_room:
        nxt["room"] = nxt_room
    elif i % 3 == 0 and t % 2 == 0 and nxt_room:
        nxt["room"] = nxt_room
    nxt["alert"] = int(nxt.get("alert", 0)) + ((i % 4) if nxt.get("room") == player else 0)
    nxt["seen"] = int(nxt.get("seen", 0)) + int(nxt.get("room") == player)
    nxt["stored_prose"] = 0
    return nxt
