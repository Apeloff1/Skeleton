"""Finite authored animation state-machine and blend evaluation reference.

The engine ticks actual transition and blend state, computes optional root
motion and emits witnessed animation events. It does not render bone meshes,
import foreign rigs or execute authored scripts.
"""
from __future__ import annotations

from copy import deepcopy

ACTIONS = ("inspect", "tick", "tick:4", "tick:16", "pause", "resume",
           "play:idle", "play:walk", "play:run", "play:jump",
           "event", "finish")
_STATES = ("idle", "walk", "run", "jump")
_ALLOWED = {
    "idle": ("walk", "jump"),
    "walk": ("idle", "run", "jump"),
    "run": ("walk", "jump"),
    "jump": ("idle", "walk"),
}


class AnimationActionError(ValueError):
    """Invalid rig, unreachable animation state or impossible transition."""


def _int(x, low, high, label):
    if type(x) is not int or not low <= x <= high:
        raise AnimationActionError("invalid animation " + label)
    return x


def default_layout(config, seed):
    _int(seed, 0, 2**31 - 1, "seed")
    names = _STATES[:min(4, config["states"])]
    return {
        "title": "Original Animation Rig " + str(seed % 10000),
        "states": [{
            "name": name,
            "duration": 2 + ((seed + i * 3) % 8),
            "root_delta": (0 if name == "idle" else 1 if name == "walk"
                           else 2 if name == "run" else 0),
            "event_tick": 1 + (seed + i) % (2 + (seed + i * 3) % 8),
        } for i, name in enumerate(names)],
        "entry": names[0],
        "rig_bones": config["bones"],
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "title", "states", "entry", "rig_bones"
    }:
        raise AnimationActionError("exact animation authored state graph required")
    name = layout["title"]
    if type(name) is not str or not 1 <= len(name) <= 100 or any(ord(c) < 32 for c in name):
        raise AnimationActionError("invalid rig name")
    bones = _int(layout["rig_bones"], 1, config["bones"], "rig bones")
    states = layout["states"]
    if type(states) is not list or not 1 <= len(states) <= min(4, config["states"]):
        raise AnimationActionError("state graph violates declared authored state budget")
    names = []
    clean = []
    for item in states:
        if type(item) is not dict or set(item) != {
            "name", "duration", "root_delta", "event_tick"
        } or item["name"] not in _STATES:
            raise AnimationActionError("unknown or executable animation node")
        if item["name"] in names:
            raise AnimationActionError("duplicate animation node")
        names.append(item["name"])
        duration = _int(item["duration"], 1, 60, "duration")
        clean.append({
            "name": item["name"], "duration": duration,
            "root_delta": _int(item["root_delta"], -8, 8, "root delta"),
            "event_tick": _int(item["event_tick"], 1, duration, "event tick"),
        })
    if layout["entry"] not in names:
        raise AnimationActionError("starting node not part of authored graph")
    return {"title": name, "states": clean,
            "entry": layout["entry"], "rig_bones": bones}


def start(config, seed):
    source = normalize_layout(config, default_layout(config, seed))
    return {
        "title": source["title"], "clips": deepcopy(source["states"]),
        "entry": source["entry"], "rig_bones": source["rig_bones"],
        "current": source["entry"], "next": None, "blend_remaining": 0,
        "time_in_clip": 0, "logical_ticks": 0, "root_position": 0,
        "playing": True, "transitions": 0, "events_seen": [],
        "events": [], "score": 0, "turn": 0,
        "finished": False, "failed": False,
        "rendered_bone_mesh": False,
    }


def apply_scene(state, config, layout):
    if state["turn"]:
        raise AnimationActionError("cannot swap rig or clip graph after playback")
    source = normalize_layout(config, layout)
    state["title"] = source["title"]
    state["clips"] = deepcopy(source["states"])
    state["entry"] = source["entry"]
    state["current"] = source["entry"]
    state["rig_bones"] = source["rig_bones"]


def _clip(state):
    return next(node for node in state["clips"] if node["name"] == state["current"])


def _advance(state, config, ticks, events):
    for _ in range(ticks):
        if state["blend_remaining"]:
            state["blend_remaining"] -= 1
            if state["blend_remaining"] == 0:
                state["current"] = state["next"]
                state["next"] = None
                state["time_in_clip"] = 0
                state["transitions"] += 1
                state["score"] += 2
                events.append("actual_blend_tree_state_transition_completed")
        clip = _clip(state)
        state["logical_ticks"] += 1
        state["time_in_clip"] = (state["time_in_clip"] + 1) % clip["duration"]
        if config["root_motion"]:
            state["root_position"] += clip["root_delta"]
        if state["time_in_clip"] == clip["event_tick"]:
            state["events_seen"].append({
                "clip": clip["name"], "tick": state["logical_ticks"]
            })
            events.append("actual_authored_animation_event_fired")
    state["events_seen"] = state["events_seen"][-32:]


def step(state, config, action):
    if action not in ACTIONS or state["finished"] or state["failed"]:
        raise AnimationActionError("unregistered or postterminal animation action")
    events = []
    if action.startswith("play:"):
        target = action.split(":")[1]
        if target not in {node["name"] for node in state["clips"]}:
            raise AnimationActionError("requested animation clip is not source-authored")
        if state["next"] is not None:
            raise AnimationActionError("clip transition already blending")
        if target == state["current"] or target not in _ALLOWED[state["current"]]:
            raise AnimationActionError("authored animation graph rejects this transition")
        if config["blend_ticks"]:
            state["next"] = target
            state["blend_remaining"] = config["blend_ticks"]
            events.append("nonzero_transition_blend_started")
        else:
            state["current"] = target
            state["time_in_clip"] = 0
            state["transitions"] += 1
            events.append("instant_valid_clip_transition_applied")
    elif action in ("tick", "tick:4", "tick:16"):
        if not state["playing"]:
            raise AnimationActionError("paused rig cannot move")
        count = 1 if action == "tick" else int(action.split(":")[1])
        _advance(state, config, count, events)
        events.append("real_animation_integer_ticks_integrated")
    elif action == "pause":
        if not state["playing"]:
            raise AnimationActionError("already paused")
        state["playing"] = False
        events.append("animation_playback_paused")
    elif action == "resume":
        if state["playing"]:
            raise AnimationActionError("already playing")
        state["playing"] = True
        events.append("animation_playback_resumed")
    elif action == "event":
        if not state["events_seen"]:
            raise AnimationActionError("no actual emitted animation events to inspect")
        state["score"] += 1
        events.append("witnessed_animation_event_processed")
    elif action == "finish":
        if not state["transitions"] or not state["events_seen"]:
            raise AnimationActionError("rig completion requires played blend and witnessed clip event")
        state["finished"] = True
        events.append("earned_original_rig_animation_trial_complete")
    else:
        events.append("source_bound_animation_state_inspected")
    state["turn"] += 1
    state["events"] = events[-64:]
    return state["events"]


__all__ = ["ACTIONS", "AnimationActionError", "default_layout",
           "normalize_layout", "start", "apply_scene", "step"]
