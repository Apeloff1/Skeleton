"""Deterministic bounded maze and RPG game-state engines.

Source-authored rules only: no native execution, publication certification,
player-behaviour prediction, remote calls, or implicit durable state.
Every mutation is replayed from configuration, seed, and validated actions.
"""
from __future__ import annotations

from .system_editors import SystemEditorError


class WorldGameError(SystemEditorError):
    """Illegal move, missing prerequisite, or exhausted finite resource."""


MAZE_ACTIONS = ("north", "south", "west", "east", "survey", "wait")
RPG_ACTIONS = (
    "talk", "accept", "explore", "travel", "ally", "oppose",
    "fight", "guard", "rest", "buy_rations", "resolve",
)


def _maze_wall(x: int, y: int, cfg: dict, seed: int, level: int) -> bool:
    """Sparse deterministic obstacles cannot sever the south/east backbone."""
    width, height = cfg["width"], cfg["height"]
    if not 0 <= x < width or not 0 <= y < height:
        return True
    if x == 0 or y == height - 1:
        return False
    topology = cfg["topology"]
    density = {"grid": 2, "circular": 1, "braided": 1,
               "moving": 2, "non_euclidean": 2}[topology]
    return ((x * 37 + y * 17 + seed * 13 + level * 19) % 13) < density


def maze_start(cfg: dict, seed: int) -> dict:
    return {
        "tick": 0, "level": 0, "position": [0, 0],
        "exit": [cfg["width"] - 1, cfg["height"] - 1],
        "key_position": [0, min(cfg["height"] - 1, 2)],
        "has_key": False, "health": 4, "max_health": 4,
        "surveyed": [[0, 0]], "visits": 1, "completed_levels": 0,
        "events": [], "finished": False, "failed": False,
    }


def maze_step(state: dict, cfg: dict, action: str) -> list[str]:
    if action not in MAZE_ACTIONS:
        raise WorldGameError("unrecognized maze action")
    events: list[str] = []
    if action in ("north", "south", "west", "east"):
        dx, dy = {"north": (0, -1), "south": (0, 1),
                  "west": (-1, 0), "east": (1, 0)}[action]
        x, y = state["position"]
        target = [x + dx, y + dy]
        if _maze_wall(target[0], target[1], cfg, state["seed"], state["level"]):
            events.append("wall_blocked")
        else:
            state["position"] = target
            state["visits"] += 1
            events.append("corridor_traversed")
            if target not in state["surveyed"]:
                state["surveyed"].append(target[:])
            if target == state["key_position"] and not state["has_key"]:
                state["has_key"] = True
                events.append("original_key_collected")
            # A low-risk optional hazard has a stable coordinate; the
            # guaranteed backbone never contains it.
            if cfg["hazards"] and target[0] > 0 and target[1] < cfg["height"] - 1:
                if (target[0] * 11 + target[1] * 23 + state["seed"]) % 17 < min(cfg["hazards"], 8):
                    state["health"] = max(0, state["health"] - 1)
                    events.append("finite_health_lost")
            if state["health"] == 0:
                state["failed"] = True
                events.append("labyrinth_run_failed")
            elif target == state["exit"]:
                if not state["has_key"]:
                    events.append("exit_requires_original_key")
                else:
                    state["completed_levels"] += 1
                    events.append("maze_level_completed")
                    if state["completed_levels"] == cfg["levels"]:
                        state["finished"] = True
                        events.append("maze_campaign_completed")
                    else:
                        state["level"] += 1
                        state["position"] = [0, 0]
                        state["has_key"] = False
                        state["surveyed"] = [[0, 0]]
                        events.append("next_original_level")
    elif action == "survey":
        events.append("bounded_local_survey")
    else:
        events.append("waited")
    state["tick"] += 1
    return events


def maze_bound_start(cfg: dict, seed: int) -> dict:
    state = maze_start(cfg, seed)
    state["seed"] = seed
    return state


def rpg_start(cfg: dict, seed: int) -> dict:
    return {
        "tick": 0, "region": seed % 4, "party": [
            {"id": i, "hp": 8} for i in range(cfg["party_size"])
        ], "rations": 6, "gold": 8, "experience": 0, "level": 1,
        "reputation": {"guild": 0, "settlers": 0, "outlaws": 0},
        "quests_completed": 0, "quest_state": "unknown",
        "quest_evidence": 0, "enemy_hp": 0, "alignment": "neutral",
        "world_flags": [], "events": [], "finished": False, "failed": False,
    }


def rpg_step(state: dict, cfg: dict, action: str) -> list[str]:
    if action not in RPG_ACTIONS:
        raise WorldGameError("unrecognized RPG action")
    events: list[str] = []
    quest = state["quest_state"]
    if action == "talk":
        if quest not in ("unknown", "completed"):
            raise WorldGameError("active quest must be resolved first")
        state["quest_state"] = "offered"
        events.append("npc_dialogue_offered")
    elif action == "accept":
        if quest != "offered":
            raise WorldGameError("quest offer is required")
        state["quest_state"] = "active"
        state["quest_evidence"] = 0
        state["enemy_hp"] = 3 + state["quests_completed"]
        events.append("quest_accepted")
    elif action == "explore":
        if quest != "active":
            raise WorldGameError("exploration evidence needs an accepted quest")
        if state["rations"] <= 0:
            raise WorldGameError("no finite rations for exploration")
        state["rations"] -= 1
        state["quest_evidence"] = min(2, state["quest_evidence"] + 1)
        events.append("regional_quest_evidence_found")
    elif action == "travel":
        if state["rations"] <= 0:
            raise WorldGameError("travel requires finite rations")
        state["rations"] -= 1
        state["region"] = (state["region"] + 1) % 4
        events.append("world_region_changed")
    elif action in ("ally", "oppose"):
        if quest != "active" or state["quest_evidence"] == 0:
            raise WorldGameError("a faction choice requires a researched quest")
        if state["alignment"] != "neutral":
            raise WorldGameError("faction choice is already committed")
        state["alignment"] = "guild" if action == "ally" else "outlaws"
        events.append("consequential_faction_choice")
    elif action == "fight":
        if quest != "active" or state["enemy_hp"] <= 0:
            raise WorldGameError("no active enemy remains")
        damage = min(5, 1 + len(state["party"]))
        state["enemy_hp"] = max(0, state["enemy_hp"] - damage)
        events.append("real_enemy_damage")
        if state["enemy_hp"] == 0:
            events.append("quest_enemy_defeated")
        else:
            # Only a living enemy retaliates, and a surviving party pays it.
            first = next((p for p in state["party"] if p["hp"] > 0), None)
            if first is not None:
                first["hp"] = max(0, first["hp"] - 1)
                events.append("party_member_damaged")
    elif action == "guard":
        events.append("party_defended")
    elif action == "rest":
        if state["rations"] == 0:
            raise WorldGameError("rest requires food")
        state["rations"] -= 1
        for member in state["party"]:
            if member["hp"] > 0:
                member["hp"] = min(8, member["hp"] + 2)
        events.append("finite_camp_recovery")
    elif action == "buy_rations":
        if state["gold"] < 2:
            raise WorldGameError("insufficient finite trade currency")
        state["gold"] -= 2
        state["rations"] += 2
        events.append("merchant_trade")
    elif action == "resolve":
        if quest != "active" or state["enemy_hp"] != 0 or state["quest_evidence"] < 1:
            raise WorldGameError("quest resolution needs research and victory")
        if state["alignment"] == "neutral":
            raise WorldGameError("quest resolution requires a consequential faction choice")
        state["quests_completed"] += 1
        state["quest_state"] = "completed"
        state["experience"] += 4
        state["gold"] += 3
        faction = state["alignment"]
        state["reputation"][faction] += 1
        state["reputation"]["settlers"] += 1 if faction == "guild" else -1
        state["world_flags"].append(f"quest-{state['quests_completed']}-{faction}")
        state["alignment"] = "neutral"
        state["level"] = min(cfg["level_cap"], 1 + state["experience"] // 12)
        events.append("persistent_quest_consequence")
        if state["quests_completed"] >= cfg["quest_depth"]:
            state["finished"] = True
            events.append("authored_campaign_resolved")
    state["tick"] += 1
    if not any(member["hp"] > 0 for member in state["party"]):
        state["failed"] = True
        events.append("party_defeated")
    return events


__all__ = [
    "WorldGameError", "MAZE_ACTIONS", "RPG_ACTIONS",
    "maze_bound_start", "maze_step", "rpg_start", "rpg_step",
]
