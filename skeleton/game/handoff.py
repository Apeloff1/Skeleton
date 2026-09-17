"""Swarm mesh handoff protocol card. Offer / accept / refuse / expire. N-cap 8.

Not the #1027 replication plane. No SSE. No network currency.
"""

from __future__ import annotations

from typing import Any


MAX_OFFERS = 8
ACTIONS = ("offer", "accept", "refuse", "expire")


class HandoffError(ValueError):
    """Mesh handoff contract violation."""


def offer(*, from_agent: str, to_agent: str, verb: str) -> dict[str, Any]:
    src = str(from_agent or "").strip()
    dst = str(to_agent or "").strip()
    action = str(verb or "").strip().lower()
    if not src or not dst or src == dst:
        raise HandoffError("handoff agents invalid")
    if action not in ACTIONS:
        raise HandoffError("unknown handoff action")
    if len(src) > 32 or len(dst) > 32:
        raise HandoffError("agent id too long")
    return {
        "kind": "handoff",
        "from": src,
        "to": dst,
        "action": action,
        "state": "offered" if action == "offer" else action + "d" if action != "expire" else "expired",
        "stored_prose": 0,
    }


def resolve(card: dict[str, Any], action: str) -> dict[str, Any]:
    current = str((card or {}).get("action") or "")
    move = str(action or "").strip().lower()
    table = {
        ("offer", "accept"): "accept",
        ("offer", "refuse"): "refuse",
        ("offer", "expire"): "expire",
    }
    nxt = table.get((current, move))
    if nxt is None:
        raise HandoffError(f"illegal handoff {current}->{move}")
    return offer(from_agent=str(card["from"]), to_agent=str(card["to"]), verb=nxt)


def session(cards: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = list(cards or [])
    if len(rows) > MAX_OFFERS:
        raise HandoffError("handoff N-cap 8")
    accepted = sum(1 for row in rows if row.get("action") == "accept")
    return {
        "kind": "mesh_handoff",
        "n": len(rows),
        "accepted": accepted,
        "cards": rows,
        "stored_prose": 0,
    }
