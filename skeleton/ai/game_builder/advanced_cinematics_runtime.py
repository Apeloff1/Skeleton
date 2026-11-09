"""Original interactive cinematic-direction timeline, with real bounded event timing.

Authorable shot sources drive camera state, cuts, cue acknowledgements, pauses,
choice gates and a replayable logical clock. This is a *reference direction
runtime*; it never claims to render video, generate audio, or execute GPU code.
"""
from __future__ import annotations

from copy import deepcopy

CUES = ("ambient", "actor", "voice", "music", "decision", "event")
ACTIONS = (
    "inspect", "play", "pause", "cue", "skip", "tick", "tick:4",
    "tick:16", "tick:64", "tick:256",
    "choose:0", "choose:1", "choose:2",
    "camera:0", "camera:1", "camera:2", "camera:3",
    "camera:4", "camera:5", "camera:6", "camera:7", "finish",
)


class CinematicActionError(ValueError):
    """An impossible timeline action or forged cinematic source."""


def _int(v, lo, hi, name):
    if type(v) is not int or not lo <= v <= hi:
        raise CinematicActionError("invalid original cinematic " + name)
    return v


def default_layout(config, seed):
    _int(seed, 0, 2**31-1, "seed")
    return {
        "title": "Original Cinematic Sequence " + str(seed % 10000),
        "shot_count": config["shots"],
        "timing_seed": seed,
        "overrides": [
            {"shot": 0, "rig": seed % config["camera_rigs"],
             "duration": min(5, config["max_shot_seconds"]),
             "cue": "actor", "interactive": False},
        ],
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "title", "shot_count", "timing_seed", "overrides"
    }:
        raise CinematicActionError("exact authored timeline source required")
    title = layout["title"]
    if type(title) is not str or not 1 <= len(title) <= 100 or any(ord(c) < 32 for c in title):
        raise CinematicActionError("invalid original sequence title")
    _int(layout["shot_count"], 1, config["shots"], "shot_count")
    _int(layout["timing_seed"], 0, 2**31-1, "timing_seed")
    overrides = layout["overrides"]
    if type(overrides) is not list or len(overrides) > 64:
        raise CinematicActionError("shot overrides require finite source array")
    clean = []
    previous = -1
    for raw in overrides:
        if type(raw) is not dict or set(raw) != {
            "shot", "rig", "duration", "cue", "interactive"
        }:
            raise CinematicActionError("shot override schema differs")
        shot = _int(raw["shot"], 0, layout["shot_count"]-1, "shot")
        if shot <= previous:
            raise CinematicActionError("shot overrides must be unique and ascending")
        previous = shot
        rig = _int(raw["rig"], 0, config["camera_rigs"]-1, "rig")
        duration = _int(raw["duration"], 1, config["max_shot_seconds"], "duration")
        if raw["cue"] not in CUES or type(raw["interactive"]) is not bool:
            raise CinematicActionError("invalid authored timed event")
        clean.append({"shot":shot, "rig":rig, "duration":duration,
                      "cue":raw["cue"], "interactive":raw["interactive"]})
    return {"title":title, "shot_count":layout["shot_count"],
            "timing_seed":layout["timing_seed"], "overrides":clean}


def _shot(state, config, index):
    if index >= state["shot_count"]:
        return None
    variant = state["timing_seed"] + index * 7
    raw = {
        "shot": index,
        "rig": variant % config["camera_rigs"],
        "duration": 1 + variant % config["max_shot_seconds"],
        "cue": CUES[variant % len(CUES)],
        "interactive": index % 9 == 4,
    }
    for override in state["overrides"]:
        if override["shot"] == index:
            return dict(override)
    return raw


def start(config, seed):
    source = normalize_layout(config, default_layout(config, seed))
    state = {
        "title":source["title"], "shot_count":source["shot_count"],
        "timing_seed":source["timing_seed"], "overrides":deepcopy(source["overrides"]),
        "shot_index":0, "current_shot":None, "remaining":0,
        "rig":0, "camera_override":None, "cue_acknowledged":False,
        "decision":None, "choices":[], "played_shots":[], "cues":[],
        "timeline_seconds":0, "turn":0, "skipped":0,
        "paused":False, "score":0, "finished":False, "failed":False,
        "events":[], "publication_certified":False,
    }
    _enter_shot(state,config)
    return state


def apply_scene(state, config, layout):
    if state["turn"] != 0:
        raise CinematicActionError("cannot change live shot custody")
    source = normalize_layout(config,layout)
    state["title"]=source["title"]
    state["shot_count"]=source["shot_count"]
    state["timing_seed"]=source["timing_seed"]
    state["overrides"]=deepcopy(source["overrides"])
    _enter_shot(state,config)


def _enter_shot(state, config):
    current = _shot(state,config,state["shot_index"])
    state["current_shot"]=current
    state["remaining"]=current["duration"] if current else 0
    state["rig"]=current["rig"] if current else 0
    state["camera_override"]=None
    state["decision"]=None
    state["cue_acknowledged"]=False


def _advance(state, config, events):
    shot=state["current_shot"]
    if shot is None:
        return
    if shot["interactive"] and state["decision"] is None:
        raise CinematicActionError("choice-required authored cut cannot be bypassed")
    state["played_shots"].append(shot["shot"])
    state["shot_index"]+=1
    events.append("actual_timeline_cut")
    _enter_shot(state,config)
    if state["current_shot"] is None:
        events.append("logical_cinematic_timeline_exhausted")


def step(state,config,action):
    if action not in ACTIONS:
        raise CinematicActionError("unregistered cinematic directing control")
    if state["finished"] or state["failed"]:
        raise CinematicActionError("terminated original sequence cannot advance")
    events=[]
    shot=state["current_shot"]
    if action.startswith("camera:"):
        if shot is None:
            raise CinematicActionError("no current shot to direct")
        rig=int(action.split(":")[1])
        if rig>=config["camera_rigs"]:
            raise CinematicActionError("camera rig was not source-authored")
        state["camera_override"]=rig
        state["rig"]=rig
        events.append("actual_camera_rig_reselected")
    elif action.startswith("choose:"):
        if shot is None or not shot["interactive"] or state["decision"] is not None:
            raise CinematicActionError("interactive cinematic choice requires pending cue")
        value=int(action[-1])
        state["decision"]=value
        state["choices"].append({"shot":shot["shot"],"choice":value})
        state["score"] += value + 1
        events.append("authored_cinematic_branch_resolved")
    elif action=="cue":
        if shot is None or state["cue_acknowledged"]:
            raise CinematicActionError("a valid unanswered shot cue is required")
        state["cue_acknowledged"]=True
        state["cues"].append({"shot":shot["shot"],"cue":shot["cue"],
                              "rig":state["rig"]})
        state["score"]+=2
        events.append("actual_cinematic_cue_marked")
    elif action=="pause":
        if state["paused"]:
            raise CinematicActionError("timeline is already paused")
        state["paused"]=True
        events.append("timeline_paused")
    elif action=="play":
        if not state["paused"]:
            raise CinematicActionError("timeline already playing")
        state["paused"]=False
        events.append("timeline_resumed")
    elif action=="skip":
        if not config["skippable"] or shot is None:
            raise CinematicActionError("non-skippable shot cannot be skipped")
        if shot["interactive"] and state["decision"] is None:
            raise CinematicActionError("unresolved cinematic choice cannot be skipped")
        state["skipped"]+=1
        _advance(state,config,events)
        events.append("player_skipped_original_shot")
    elif action.startswith("tick"):
        if state["paused"] or shot is None:
            raise CinematicActionError("paused or exhausted timeline cannot advance")
        remaining=1 if action=="tick" else int(action.split(":")[1])
        while remaining>0 and state["current_shot"] is not None:
            shot=state["current_shot"]
            consume=min(remaining,state["remaining"])
            state["remaining"]-=consume
            state["timeline_seconds"]+=consume
            remaining-=consume
            if state["remaining"]==0:
                if shot["interactive"] and state["decision"] is None:
                    events.append("awaiting_interactive_cinematic_choice")
                    break
                _advance(state,config,events)
        events.append("real_integer_timeline_time_advanced")
    elif action=="finish":
        if state["current_shot"] is not None or len(state["played_shots"])!=state["shot_count"]:
            raise CinematicActionError("all authored shots must actually be advanced")
        state["finished"]=True
        state["score"]+=10
        events.append("earned_cinematic_storyboard_completion")
    elif action=="inspect":
        events.append("original_timeline_state_observed")
    state["turn"]+=1
    state["events"]=events
    return events


__all__=["CUES","ACTIONS","CinematicActionError","default_layout",
         "normalize_layout","start","apply_scene","step"]
