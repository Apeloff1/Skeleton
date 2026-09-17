"""Dialogue as pointer clauses. No stored sentence."""

from __future__ import annotations

from typing import Any


class DialogueError(ValueError):
    pass


TOPICS = (
    "spawn_hint", "scrap_hint", "heat_warn", "forge_tip", "sleep_gate",
    "dream_cut", "lock_ask", "extract_ready", "bait_offer", "patrol_warn",
    "coil_bind", "barter_open", "quest_mark", "warp_once", "fog_warn", "shaft_down",
)


def start(topic: str) -> dict[str, Any]:
    if topic not in TOPICS:
        raise DialogueError(topic)
    idx = TOPICS.index(topic)
    return {"topic": topic, "node": f"d{idx:02d}_0", "closed": False, "stored_prose": 0}


def step(card: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    topic = str(card.get("topic") or "")
    if topic not in TOPICS:
        raise DialogueError(topic)
    nxt = dict(card)
    node = str(nxt.get("node") or "")
    try:
        seq = int(node.split("_")[-1])
    except ValueError as exc:
        raise DialogueError("node") from exc
    need = ("heat", "scrap", "key", "sleep", "xp", "tokens")[seq % 6]
    need_n = seq % 4
    if int(state.get(need, 0)) < need_n:
        nxt["blocked"] = True
        return nxt
    nxt["blocked"] = False
    nxt["node"] = f"d{TOPICS.index(topic):02d}_{min(5, seq + 1)}"
    nxt["closed"] = seq + 1 >= 5
    nxt["stored_prose"] = 0
    return nxt
