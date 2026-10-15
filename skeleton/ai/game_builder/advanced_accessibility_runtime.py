"""Executable original input-remap and accessibility preference reference.

Simulates actual remapped control dispatch, alternative color-independent
cues, subtitle text, and safe motion/transcription preferences. No fake
screen-reader hardware, accessibility compliance or certified WCAG audits.
"""
from __future__ import annotations

from copy import deepcopy

ACTIONS = ("inspect", "trigger:jump", "trigger:confirm",
           "remap:jump:confirm", "remap:confirm:jump", "reset_remap",
           "cue:visual", "cue:audio", "show:subtitle",
           "toggle:motion", "toggle:subtitles",
           "font:up", "font:down", "review", "finish")
CONTROLS = ("jump", "confirm")
CUE_MODES = ("symbol", "shape", "audio", "subtitle")


class AccessibilityActionError(ValueError):
    """Unusable remap, missing alternative cue or illegal player preference."""


def _int(x, low, high, name):
    if type(x) is not int or not low <= x <= high:
        raise AccessibilityActionError("invalid accessibility " + name)
    return x


def default_layout(config, seed):
    _int(seed, 0, 2**31-1, "seed")
    return {
        "title": "Original Accessible Controls " + str(seed % 10000),
        "source_controls": ["jump", "confirm"],
        "label_jump": "Jump or climb",
        "label_confirm": "Confirm action",
        "color_cue": "shape" if config["color_independent_cues"] else "audio",
        "subtitle": "An original nonviolent scene begins.",
    }


def normalize_layout(config, layout):
    keys = {"title", "source_controls", "label_jump",
            "label_confirm", "color_cue", "subtitle"}
    if type(layout) is not dict or set(layout) != keys:
        raise AccessibilityActionError("exact accessible controls source required")
    def label(text):
        return (type(text) is str and 1 <= len(text) <= 120
                and all(ord(char) >= 32 for char in text))
    if not all(label(layout[key]) for key in ("title", "label_jump",
                                              "label_confirm", "subtitle")):
        raise AccessibilityActionError("accessible prose labels are missing")
    if (type(layout["source_controls"]) is not list or
            layout["source_controls"] != ["jump", "confirm"]):
        raise AccessibilityActionError("complete original action vocabulary required")
    if layout["color_cue"] not in CUE_MODES:
        raise AccessibilityActionError("undeclared cue channel")
    if config["color_independent_cues"] and layout["color_cue"] not in ("shape", "symbol"):
        raise AccessibilityActionError("independent visual shape or symbol is required")
    return {
        "title": layout["title"], "source_controls": list(CONTROLS),
        "label_jump": layout["label_jump"], "label_confirm": layout["label_confirm"],
        "color_cue": layout["color_cue"], "subtitle": layout["subtitle"],
    }


def start(config, seed):
    source = normalize_layout(config, default_layout(config, seed))
    return {
        "title": source["title"], "labels": {
            "jump": source["label_jump"], "confirm": source["label_confirm"]
        },
        "color_cue": source["color_cue"], "subtitle": source["subtitle"],
        "mapping": {"jump": "jump", "confirm": "confirm"},
        "subtitles": config["subtitles"], "reduced_motion": config["reduced_motion"],
        "font_scale": config["font_scale_percent"],
        "dispatches": [], "cues": [], "subtitle_log": [],
        "remaps": 0, "alternatives_used": 0, "score": 0, "turn": 0,
        "finished": False, "failed": False, "events": [],
        "native_accessibility_certified": False,
    }


def apply_scene(state, config, layout):
    if state["turn"]:
        raise AccessibilityActionError("cannot rewrite control labels during player activity")
    source = normalize_layout(config,layout)
    state["title"] = source["title"]
    state["labels"] = {"jump":source["label_jump"],"confirm":source["label_confirm"]}
    state["color_cue"] = source["color_cue"]
    state["subtitle"] = source["subtitle"]


def step(state, config, action):
    if action not in ACTIONS or state["finished"] or state["failed"]:
        raise AccessibilityActionError("undeclared accessible player control")
    events = []
    if action.startswith("remap:"):
        if not config["full_remap"]:
            raise AccessibilityActionError("source does not allow game action remapping")
        _, src, dst = action.split(":")
        new = dict(state["mapping"])
        # Swap destinations atomically: no user command becomes inaccessible.
        other = next((key for key, target in new.items() if target == dst),None)
        if other is None:
            raise AccessibilityActionError("unmapped button cannot be bound")
        new[other] = new[src]
        new[src] = dst
        if len(set(new.values())) != len(CONTROLS):
            raise AccessibilityActionError("ambiguous physical button mapping")
        state["mapping"] = new
        state["remaps"] += 1
        events.append("real_bijective_input_remap_applied")
    elif action == "reset_remap":
        if not config["full_remap"]:
            raise AccessibilityActionError("remapping not admitted")
        state["mapping"] = {"jump":"jump","confirm":"confirm"}
        events.append("user_control_map_reset_to_original")
    elif action.startswith("trigger:"):
        physical = action.split(":")[1]
        logical = next(
            (command for command, key in state["mapping"].items() if key == physical),
            None
        )
        if logical is None:
            raise AccessibilityActionError("user button has no bound action")
        state["dispatches"].append({
            "physical":physical, "logical":logical, "step":state["turn"]
        })
        state["dispatches"] = state["dispatches"][-32:]
        state["score"] += 1
        events.append("actual_user_input_dispatched_through_remapped_binding")
    elif action == "cue:visual":
        mode = state["color_cue"]
        if config["color_independent_cues"] and mode not in ("shape", "symbol"):
            raise AccessibilityActionError("color-only feedback forbidden by source")
        state["cues"].append(mode)
        state["alternatives_used"] += 1
        events.append(
            "authored_shape_or_symbol_cue_emitted"
            if mode in ("shape", "symbol") else "nonvisual_audio_cue_requested"
        )
    elif action == "cue:audio":
        state["cues"].append("audio")
        events.append("alternative_audio_cue_requested_not_rendered")
    elif action == "show:subtitle":
        if not state["subtitles"]:
            raise AccessibilityActionError("subtitles are disabled in player preferences")
        state["subtitle_log"].append(state["subtitle"])
        state["alternatives_used"] += 1
        events.append("authored_caption_text_delivered")
    elif action == "toggle:motion":
        state["reduced_motion"] = not state["reduced_motion"]
        events.append("actual_reduced_motion_setting_toggled")
    elif action == "toggle:subtitles":
        state["subtitles"] = not state["subtitles"]
        events.append("actual_subtitle_preference_toggled")
    elif action in ("font:up", "font:down"):
        increment = 10 if action == "font:up" else -10
        candidate = state["font_scale"] + increment
        if not 75 <= candidate <= 300:
            raise AccessibilityActionError("new font size exceeds safe rendering envelope")
        state["font_scale"] = candidate
        events.append("user_font_scale_setting_changed")
    elif action == "review":
        if not state["dispatches"]:
            raise AccessibilityActionError("an actual remapped action must execute before review")
        state["score"] += 2
        events.append("actual_input_custody_reviewed")
    elif action == "finish":
        if not state["dispatches"] or not state["alternatives_used"]:
            raise AccessibilityActionError("accessible trial needs both gameplay input and alternate cue")
        state["finished"] = True
        events.append("earned_accessible_controls_walkthrough_complete")
    else:
        events.append("accessibility_preferences_inspected")
    state["cues"] = state["cues"][-32:]
    state["subtitle_log"] = state["subtitle_log"][-16:]
    state["turn"] += 1
    state["events"] = events
    return events


__all__ = ["ACTIONS", "AccessibilityActionError", "default_layout",
           "normalize_layout", "start", "apply_scene", "step"]
