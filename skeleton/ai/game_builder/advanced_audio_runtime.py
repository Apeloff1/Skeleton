"""Source-authored logical audio mixer and finite cue scheduler.

Voices consume actual authored channels; priority stealing and sidechain
ducking are deterministic, scheduled time advances in integer samples, and
spatial gain is computed without fake sound output. No wave synthesis or
sound card access is claimed by this reference runtime.
"""
from __future__ import annotations

from copy import deepcopy

ACTIONS = ("inspect", "tick", "tick:1024", "tick:4096",
           "play:0", "play:1", "play:2", "play:3",
           "stop:0", "stop:1", "stop:2", "stop:3",
           "layer:0", "layer:1", "layer:2", "layer:3",
           "near", "far", "mute", "unmute", "mix", "finish")


class AudioActionError(ValueError):
    """Unsupported source, voice budget, score or cue command."""


def _int(x, lo, hi, label):
    if type(x) is not int or not lo <= x <= hi:
        raise AudioActionError("invalid audio " + label)
    return x


def default_layout(config, seed):
    _int(seed, 0, 2**31 - 1, "seed")
    clips = [
        {
            "id": i, "samples": min(config["sample_rate"] * 2,
                                    config["sample_rate"] // 8 * (i + 2)),
            "priority": i + 1, "spatial": bool(config["spatial_audio"] and i % 2),
            "layer": i % config["dynamic_layers"],
        }
        for i in range(min(4, config["dynamic_layers"]))
    ]
    return {"title": "Original Soundstage " + str(seed % 10000),
            "clips": clips, "listener": 0}


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {"title", "clips", "listener"}:
        raise AudioActionError("exact finite original audio mix source required")
    title = layout["title"]
    if type(title) is not str or not 1 <= len(title) <= 100 or any(ord(c) < 32 for c in title):
        raise AudioActionError("invalid original mix title")
    _int(layout["listener"], 0, 100, "listener position")
    clips = layout["clips"]
    if type(clips) is not list or not 1 <= len(clips) <= min(4, config["dynamic_layers"]):
        raise AudioActionError("authored sound palette exceeds enabled layers")
    clean = []
    for i, item in enumerate(clips):
        if type(item) is not dict or set(item) != {
            "id", "samples", "priority", "spatial", "layer",
        }:
            raise AudioActionError("exact source-authored clip fields required")
        if type(item["spatial"]) is not bool or (
            item["spatial"] and not config["spatial_audio"]
        ):
            raise AudioActionError("spatial routing not admitted by source")
        clean.append({
            "id": _int(item["id"], i, i, "clip id"),
            "samples": _int(item["samples"], 128, config["sample_rate"] * 10, "clip length"),
            "priority": _int(item["priority"], 1, 10, "priority"),
            "spatial": item["spatial"],
            "layer": _int(item["layer"], 0, config["dynamic_layers"] - 1, "layer"),
        })
    return {"title": title, "clips": clean, "listener": layout["listener"]}


def start(config, seed):
    source = normalize_layout(config, default_layout(config, seed))
    return {
        "title": source["title"], "clips": deepcopy(source["clips"]),
        "listener": source["listener"], "voices": [], "active_layers": [],
        "logical_sample": 0, "muted": False, "voice_seq": 0, "played": 0,
        "stolen": 0, "completed": 0, "mixed": 0, "score": 0, "turn": 0,
        "finished": False, "failed": False, "events": [],
        "actual_audio_output": False, "sample_rate": config["sample_rate"],
    }


def apply_scene(state, config, layout):
    if state["turn"]:
        raise AudioActionError("cannot alter original audio source during playback")
    source = normalize_layout(config, layout)
    state["title"], state["listener"] = source["title"], source["listener"]
    state["clips"] = deepcopy(source["clips"])


def _cue(state, clip_id):
    for clip in state["clips"]:
        if clip["id"] == clip_id:
            return clip
    raise AudioActionError("source cue not in local original-game audio palette")


def _mix(state, config, events):
    # Integer gain domain 0..100. Explicit mute and per-voice attenuation
    # prevent decorative 'played' counters from claiming emitted sound.
    peak = 0
    for voice in state["voices"]:
        clip = _cue(state, voice["id"])
        gain = 0 if state["muted"] else max(
            0, 100 - abs(state["listener"] - voice["position"]) * 2
        ) if clip["spatial"] else (0 if state["muted"] else 100)
        if config["mix_strategy"] == "sidechain" and clip["priority"] < 3:
            if any(_cue(state, other["id"])["priority"] >= 3
                   for other in state["voices"] if other is not voice):
                gain = gain // 4
        voice["gain"] = gain
        peak = max(peak, gain)
    state["mixed"] += 1
    state["score"] += peak // 20
    events.append("real_bounded_gain_mix_evaluated")
    return peak


def step(state, config, action):
    if action not in ACTIONS or state["finished"] or state["failed"]:
        raise AudioActionError("unregistered soundstage command")
    events = []
    if action.startswith("play:"):
        clip = _cue(state, int(action[-1]))
        if len(state["voices"]) >= config["channels"]:
            if config["mix_strategy"] == "fixed":
                raise AudioActionError("fixed mixer has no free authored audio channels")
            weakest = min(state["voices"], key=lambda v: (_cue(state, v["id"])["priority"], v["seq"]))
            if _cue(state, weakest["id"])["priority"] > clip["priority"]:
                raise AudioActionError("low priority sound cannot steal important voice")
            state["voices"].remove(weakest)
            state["stolen"] += 1
            events.append("actual_channel_priority_voice_stolen")
        state["voice_seq"] += 1
        state["voices"].append({
            "id": clip["id"], "seq": state["voice_seq"],
            "remaining": clip["samples"], "position": min(100, clip["id"] * 20),
            "gain": 0,
        })
        state["played"] += 1
        _mix(state, config, events)
        events.append("source_cue_scheduled_on_real_channel")
    elif action.startswith("stop:"):
        cid = int(action[-1])
        voices = [v for v in state["voices"] if v["id"] != cid]
        if len(voices) == len(state["voices"]):
            raise AudioActionError("cannot stop an unheard inactive clip")
        state["voices"] = voices
        _mix(state, config, events)
        events.append("real_audio_channel_released")
    elif action.startswith("layer:"):
        layer = int(action[-1])
        if layer >= config["dynamic_layers"]:
            raise AudioActionError("requested music layer exceeds authoring budget")
        if layer in state["active_layers"]:
            state["active_layers"].remove(layer)
        else:
            state["active_layers"].append(layer)
            state["active_layers"].sort()
        events.append("dynamic_original_music_layer_toggled")
    elif action in ("tick", "tick:1024", "tick:4096"):
        amount = 1 if action == "tick" else int(action.split(":")[1])
        state["logical_sample"] += amount
        for v in state["voices"]:
            v["remaining"] -= amount
        completed = len([v for v in state["voices"] if v["remaining"] <= 0])
        state["completed"] += completed
        state["voices"] = [v for v in state["voices"] if v["remaining"] > 0]
        if completed:
            events.append("actual_logical_clip_duration_expired")
        _mix(state, config, events)
        events.append("real_integer_sample_clock_advanced")
    elif action in ("near", "far"):
        state["listener"] = max(0, state["listener"] - 10) if action == "near" else min(
            100, state["listener"] + 10)
        _mix(state, config, events)
        events.append("spatial_listener_position_changed")
    elif action == "mute" or action == "unmute":
        desired = action == "mute"
        if state["muted"] == desired:
            raise AudioActionError("redundant mute operation")
        state["muted"] = desired
        _mix(state, config, events)
        events.append("actual_logical_audio_mute_applied")
    elif action == "mix":
        _mix(state, config, events)
    elif action == "finish":
        if not state["played"] or state["voices"]:
            raise AudioActionError("original soundstage completion requires played and expired/stopped cues")
        state["finished"] = True
        events.append("earned_audio_event_timeline_trial_complete")
    else:
        events.append("original_audio_source_state_inspected")
    state["turn"] += 1
    state["events"] = events[-48:]
    return state["events"]


__all__ = ["ACTIONS", "AudioActionError", "default_layout",
           "normalize_layout", "start", "apply_scene", "step"]
