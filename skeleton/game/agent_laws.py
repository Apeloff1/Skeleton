"""Sixteen agents. Mood clocks. No network."""

from __future__ import annotations

from typing import Any


MOODS = ("idle", "patrol", "chase", "retreat", "extract")


class AgentLawError(ValueError):
    pass


def agent_blank(index: int) -> dict[str, Any]:
    if index < 0 or index > 15:
        raise AgentLawError("index")
    floor, ri = divmod(index, 4)
    return {
        "id": f"ag{index:02d}",
        "room": f"f{floor}r{ri}",
        "floor": floor,
        "mood": "patrol",
        "heat": index % 8,
        "stored_prose": 0,
    }


def agent_step(agent: dict[str, Any], player_room: str, t: int) -> dict[str, Any]:
    nxt = dict(agent)
    mood = str(nxt.get("mood") or "idle")
    if player_room == nxt.get("room") and mood != "retreat":
        nxt["mood"] = "chase"
    elif int(t) % 5 == int(str(nxt.get("id") or "ag00")[-1]) % 5:
        nxt["mood"] = "patrol"
    if nxt["mood"] == "chase":
        nxt["room"] = player_room
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + ((t % 3) - 1)))
    nxt["stored_prose"] = 0
    return nxt


def agent_alert(agent: dict[str, Any]) -> bool:
    return str(agent.get("mood")) == "chase" and int(agent.get("heat", 0)) >= 4


def squad_blank() -> list[dict[str, Any]]:
    return [agent_blank(i) for i in range(16)]


def squad_tick(squad: list[dict[str, Any]], player_room: str, t: int) -> list[dict[str, Any]]:
    return [agent_step(agent, player_room, t) for agent in squad]


def squad_alerts(squad: list[dict[str, Any]]) -> int:
    return sum(1 for agent in squad if agent_alert(agent))


def card(squad: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": "squad", "n": len(squad), "alerts": squad_alerts(squad), "stored_prose": 0}
