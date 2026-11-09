"""Original story-choice engine with replayable branch, canon and ending effects.

A bounded authored story document determines available choices, their concrete
state effects and ending identities. Player choices change the world, not merely
a decorative prompt. The canonical advanced-session runtime remains the only
source of replay/receipt authority; no model/provider or arbitrary script runs.
"""
from __future__ import annotations

import re
from copy import deepcopy

THEMES = ("community", "discovery", "conflict", "legacy", "wilderness", "machine")
CHOICES = ("aid", "investigate", "negotiate", "seize", "withdraw", "protect")
ACTIONS = ("inspect", "review", "wait", "checkpoint", "resolve",
           "explore", "retire") + tuple("choose:" + str(i) for i in range(3))


class NarrativeActionError(ValueError):
    """Malformed source, invalid narrative choice or unearned ending."""


def _integer(value, lo, hi, field):
    if type(value) is not int or not lo <= value <= hi:
        raise NarrativeActionError("invalid original story " + field)
    return value


def default_layout(config, seed):
    _integer(seed, 0, 2**31-1, "seed")
    count = 1 if config["structure"] == "linear" else (
        2 if config["structure"] == "branching" else 3)
    beats = []
    for index in range(config["branch_depth"]):
        first = (seed + index * 5) % len(CHOICES)
        # Distinct source-authored effects rather than identical mock branches.
        actions = [CHOICES[(first + 2 * n) % len(CHOICES)] for n in range(count)]
        beats.append({
            "id": index, "theme": THEMES[(seed + index) % len(THEMES)],
            "choices": actions,
        })
    return {
        "title": "Original Chronicle " + str(seed % 10000),
        "beats": beats,
        "endings": ["ending-" + str(n).zfill(3)
                    for n in range(config["ending_count"])],
        "home": "commons",
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {"title", "beats", "endings", "home"}:
        raise NarrativeActionError("exact original narrative layout required")
    if (type(layout["title"]) is not str or not 1 <= len(layout["title"]) <= 100
            or any(ord(c) < 32 for c in layout["title"])):
        raise NarrativeActionError("invalid authored story title")
    if layout["home"] not in ("commons", "frontier", "citadel"):
        raise NarrativeActionError("unknown non-canonical starting settlement")
    beats = layout["beats"]
    if type(beats) is not list or len(beats) != config["branch_depth"]:
        raise NarrativeActionError("actual authored beat count differs from editor")
    count = 1 if config["structure"] == "linear" else (
        2 if config["structure"] == "branching" else 3)
    cleaned = []
    for index, raw in enumerate(beats):
        if type(raw) is not dict or set(raw) != {"id", "theme", "choices"}:
            raise NarrativeActionError("exact authored story beat fields required")
        _integer(raw["id"], index, index, "beat identity")
        if raw["theme"] not in THEMES:
            raise NarrativeActionError("unknown story theme")
        choices = raw["choices"]
        if (type(choices) is not list or len(choices) != count
                or len(set(choices)) != count or
                any(choice not in CHOICES for choice in choices)):
            raise NarrativeActionError("missing or duplicated meaningful branch")
        cleaned.append({"id": index, "theme": raw["theme"],
                        "choices": list(choices)})
    endings = layout["endings"]
    if (type(endings) is not list or len(endings) != config["ending_count"]
            or len(set(endings)) != len(endings) or
            any(type(e) is not str or not re.fullmatch(r"ending-[0-9]{3}", e)
                for e in endings)):
        raise NarrativeActionError("missing exact finite named narrative endings")
    return {"title": layout["title"], "beats": cleaned,
            "endings": list(endings), "home": layout["home"]}


def start(config, seed):
    story = normalize_layout(config, default_layout(config, seed))
    return {
        "title": story["title"], "home": story["home"], "beats": story["beats"],
        "endings": story["endings"], "structure": config["structure"],
        "beat": 0, "turn": 0, "chapter": 1, "seed": seed,
        "choices_made": [], "flags": [], "knowledge": 0, "trust": 0,
        "power": 0, "risk": 0, "reputation": 0, "faction": "commons",
        "health": 10, "score": 0, "canon": [], "checkpoint": False,
        "completed": False, "ending": None, "postgame_events": 0,
        "finished": False, "failed": False, "events": [],
    }


def apply_scene(state, config, layout):
    if state["turn"] != 0:
        raise NarrativeActionError("cannot replace witnessed authored choices")
    story = normalize_layout(config, layout)
    state["title"], state["home"] = story["title"], story["home"]
    state["beats"], state["endings"] = deepcopy(story["beats"]), list(story["endings"])


def _choice_effect(state, effect, theme):
    if effect in ("aid", "protect"):
        state["trust"] += 2
        state["reputation"] += 1
        state["faction"] = "commons"
    elif effect == "investigate":
        state["knowledge"] += 2
        state["risk"] += 1
        state["faction"] = "scholars"
    elif effect == "negotiate":
        state["knowledge"] += 1
        state["trust"] += 1
        state["faction"] = "mediators"
    elif effect == "seize":
        state["power"] += 2
        state["risk"] += 2
        state["faction"] = "citadel"
    elif effect == "withdraw":
        state["risk"] = max(0, state["risk"] - 2)
        state["knowledge"] += 1
    if state["risk"] >= 12:
        state["health"] = max(0, state["health"] - 1)
        state["risk"] -= 6
    state["score"] += (2 * state["trust"] + state["knowledge"]
                       + state["power"] - state["risk"])
    name = theme + ":" + effect
    if name not in state["flags"]:
        state["flags"].append(name)
        state["flags"].sort()


def step(state, config, action):
    if action not in ACTIONS:
        raise NarrativeActionError("unregistered authored story command")
    if state["finished"] or state["failed"]:
        raise NarrativeActionError("terminated original story cannot advance")
    events = []
    depth = len(state["beats"])
    if action.startswith("choose:"):
        if state["completed"] or state["beat"] >= depth:
            raise NarrativeActionError("choices require an unfinished authored beat")
        branch = int(action[-1])
        beat = state["beats"][state["beat"]]
        if branch >= len(beat["choices"]):
            raise NarrativeActionError("unavailable narrative branch cannot happen")
        effect = beat["choices"][branch]
        flag = beat["theme"] + ":" + effect
        if flag not in state["flags"] and len(state["flags"]) >= config["state_flags"]:
            retired = state["flags"].pop(0)
            state["canon"].append({
                "beat":state["beat"],
                "fact":"retired-active-flag:"+retired,
                "source":"bounded_active_flags_historical_canon_retained",
            })
            events.append("historical_canon_preserved_when_active_flag_evicted")
        _choice_effect(state, effect, beat["theme"])
        old = state["beat"]
        state["beat"] = min(depth, old + (2 if depth >= 96 else 1))
        state["chapter"] = state["beat"] // 8 + 1
        state["choices_made"].append({
            "beat": old, "choice": branch, "effect": effect,
            "theme": beat["theme"], "consequence": flag,
            "health": state["health"], "faction": state["faction"],
        })
        state["canon"].append({
            "beat": old, "fact": flag,
            "source": "witnessed_player_choice",
        })
        events.extend(("original_choice_performed", "canon_consequence_recorded"))
        if state["beat"] == depth:
            events.append("authored_fork_depth_reached")
    elif action == "checkpoint":
        if state["beat"] < max(1, depth // 2):
            raise NarrativeActionError("story checkpoint requires earned prior decisions")
        if not state["checkpoint"]:
            state["checkpoint"] = True
        events.append("earned_story_checkpoint")
    elif action == "resolve":
        if state["completed"] or state["beat"] != depth or not state["choices_made"]:
            raise NarrativeActionError("ending requires a completed actual authored route")
        if state["health"] <= 0:
            raise NarrativeActionError("lost narrative protagonist cannot resolve")
        scores = (state["trust"] * 3 + state["knowledge"] * 5
                  + state["power"] * 7 + state["reputation"] + state["seed"])
        index = scores % len(state["endings"])
        state["ending"] = state["endings"][index]
        state["completed"] = True
        state["score"] += 20
        events.extend(("earned_original_story_ending", state["ending"]))
        if not config["postgame_play"]:
            state["finished"] = True
    elif action == "explore":
        if not state["completed"] or not config["postgame_play"]:
            raise NarrativeActionError("postgame requires an actual completed story")
        state["postgame_events"] += 1
        state["knowledge"] += 1
        events.append("original_postgame_world_persisted")
    elif action == "retire":
        if not state["completed"] or not config["postgame_play"]:
            raise NarrativeActionError("optional retirement requires earned open ending")
        state["finished"] = True
        events.append("voluntary_original_story_retirement")
    elif action == "inspect":
        events.append("authored_story_state_inspected")
    elif action == "review":
        events.append("previous_branch_consequences_reviewed")
    elif action == "wait":
        events.append("narrative_world_clock_advanced")
    state["turn"] += 1
    if state["health"] <= 0:
        state["failed"] = True
        events.append("original_story_protagonist_lost")
    if state["turn"] >= 128 and not state["completed"] and not state["finished"]:
        state["failed"] = True
        events.append("narrative_authoring_episode_exhausted")
    state["events"] = events
    return events


__all__ = ["THEMES", "CHOICES", "ACTIONS", "NarrativeActionError",
           "default_layout", "normalize_layout", "start", "apply_scene", "step"]
