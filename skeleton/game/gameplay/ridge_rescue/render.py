"""Deterministic accessible ASCII scene renderer with bounded local vision."""
from __future__ import annotations
from .schema import World

GLYPHS = {".": "·", "#": "█", "~": "≈", "^": "▲"}

def render_map(world: World, state: dict, *, radius: int = 4, reveal: bool = False) -> str:
    if type(radius) is not int or not 0 <= radius <= 24:
        raise ValueError("invalid vision radius")
    here = tuple(state["position"])
    visible: dict[tuple[int, int], str] = {}
    for y, row in enumerate(world.rows):
        for x, terrain in enumerate(row):
            if reveal or abs(x - here[0]) + abs(y - here[1]) <= radius:
                visible[(x, y)] = GLYPHS[terrain]
    for ident, kind, at, _ in world.resources:
        if state["resources"][ident] > 0 and at in visible:
            visible[at] = {"wood": "W", "ore": "O", "herb": "H"}[kind]
    for ident, at in world.civilians:
        if state["civilians"][ident] == "waiting" and at in visible:
            visible[at] = "C"
    for ident, raider in state["raiders"].items():
        at = tuple(raider["at"])
        if raider["health"] > 0 and at in visible:
            visible[at] = "R"
    if world.shelter in visible:
        visible[world.shelter] = "S"
    if here in visible:
        visible[here] = "@"
    lines = ["".join(visible.get((x, y), " ") for x in range(world.width)) for y in range(world.height)]
    lines.append(f"Turn {state['turn']}/{world.max_turns}  HP {state['health']}  Stamina {state['stamina']}  Credits {state['credits']}  {state['status']}")
    return "\n".join(lines)

def legend() -> str:
    return "@ player | C civilian | R raider | S shelter | W wood | O ore | H herb | ▲ ridge | █ wall | ≈ water | · path"
