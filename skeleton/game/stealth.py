"""Stealth field. Detection = LOS in-room or shared-node + heat + mood."""

from __future__ import annotations

from typing import Any

from skeleton.game.layouts import room as layout_room
from skeleton.game.los import visible


class StealthError(ValueError):
    """Stealth contract violation."""


def detect(
    *,
    player_room: str,
    stalker_room: str,
    stalker_mood: str,
    heat: int,
    player_xy: tuple[int, int] = (1, 1),
    stalker_xy: tuple[int, int] = (4, 3),
    seed: int = 8847291,
    room_kind: str = "scavenge",
    room_index: int = 1,
) -> dict[str, Any]:
    if heat < 0:
        raise StealthError("heat invalid")
    same = player_room == stalker_room
    seen = False
    if same:
        layout = layout_room(seed, room_index, room_kind)
        seen = visible(layout, stalker_xy, player_xy)
    score = 0
    if same:
        score += 4
    if seen:
        score += 3
    if stalker_mood == "chase":
        score += 2
    if heat >= 12:
        score += 1
    alert = score >= 5
    return {
        "kind": "stealth",
        "same_room": same,
        "los": seen,
        "score": score,
        "alert": alert,
        "stored_prose": 0,
    }
