"""Read-only guidance for the canonical Cinder Ridge consumer game.

All text is derived from replay-verified game state. Hints are explicitly
advisory: dynamic raiders, stamina and storms can invalidate static routes.
These helpers never mutate, advance or persist a turn.
"""
from __future__ import annotations

from .guidance import hint
from .schema import parse_world


def status_panel(verified: dict) -> str:
    campaign = verified["campaign"]
    index = verified["index"]
    if index >= len(campaign["episodes"]):
        endings = [entry["state"]["status"] for entry in verified["session"]["completed"]]
        return "Earned endings: " + ", ".join(endings)
    episode = campaign["episodes"][index]
    state = verified["state"]
    if state is None:
        return "Chapter state unavailable; no action is permitted."
    rescued = sum(value == "rescued" for value in state["civilians"].values())
    total = len(state["civilians"])
    beacon = "lit" if state["flags"]["beacon"] else "unlit"
    return (
        f"Story: {episode['title']} | Required ending: {episode['ending']}\n"
        f"Objective: rescue civilians ({rescued}/{total}), reach the shelter, "
        f"and earn the required evacuation choice.\n"
        f"Turn: {state['turn']}/{episode['world']['max_turns']} | "
        f"Health: {state['health']}/10 | Stamina: {state['stamina']}/8 | "
        f"Beacon: {beacon}\n"
        "To earn protect, craft a signal from resources and light it at the shelter. "
        "Rest restores stamina; hazards and enemies still advance."
    )


def navigation_hint(verified: dict) -> str:
    if verified["status"] != "playing" or verified["state"] is None:
        return "No active route; a failed chapter can be retried, or a completed game exported."
    episode = verified["campaign"]["episodes"][verified["index"]]
    world = parse_world(episode["world"])
    result = hint(world, verified["state"])
    if result["kind"] == "blocked":
        return "Advisory only: no safe static path found. Try a different action or recover stamina."
    steps = result.get("directions", [])
    if steps:
        advice = "Next suggested movement: " + steps[0]
    else:
        advice = "Target is adjacent; inspect the offered actions."
    return (
        f"Advisory only (not a victory guarantee): {result['kind']} "
        f"{result['target']}, static distance {result['distance']}. {advice}. "
        "Moving enemies and hazards can change the route."
    )


def recent_events(verified: dict) -> str:
    state = verified["state"]
    if state is None:
        completed = verified["session"]["completed"]
        state = completed[-1]["state"] if completed else None
    if state is None:
        return "No journal events."
    events = state["events"][-5:]
    return "Recent events: " + (", ".join(events) if events else "(no actions yet)")

def action_label(action: dict) -> str:
    """Human-readable labels only for actions offered by the canonical engine."""
    verb = action["verb"]
    if verb == "move":
        return "Walk " + action["direction"]
    if verb == "gather":
        return "Gather resources at " + action["target"]
    if verb == "craft":
        return "Craft " + action["item"]
    if verb == "attack":
        return "Defend against " + action["target"]
    if verb == "rescue":
        return "Rescue " + action["target"]
    if verb == "rest":
        return "Rest and recover stamina (time still advances)"
    if verb == "signal":
        return "Light the shelter beacon"
    if verb == "evacuate":
        return "Evacuate and choose " + action["choice"] + " ending"
    if verb == "trade":
        return "Trade: " + action["side"] + " " + action["item"]
    # Unknown verbs are not made into commands; the canonical engine decides
    # which actions exist. Fail closed instead of inventing a display contract.
    raise ValueError("unsupported canonical action label")
