"""Deterministic playable controller/menu/HUD navigation reference subsystem.

Focus moves in a finite authored widget graph, inventory/maps create real
menu stack transitions, and screen-reader labels and layout scale are tracked.
This model describes interactions; it is not a substitute for rendered native
UI, screen readers or viewport measurements.
"""
from __future__ import annotations

from copy import deepcopy

ACTIONS = ("inspect", "left", "right", "up", "down", "select", "back",
           "open:inventory", "open:map", "toggle:0", "toggle:1",
           "toggle:2", "toggle:3", "scale:up", "scale:down",
           "hint", "finish")


class HudActionError(ValueError):
    """Focus leak, impossible menu transition or invalid authored widget."""


def _int(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise HudActionError("invalid UI " + name)
    return value


def default_layout(config, seed):
    _int(seed, 0, 2**31-1, "seed")
    visible = min(config["hud_panels"], 4)
    focus = min(config["focus_targets"], 8)
    return {
        "title": "Original Player Interface " + str(seed % 10000),
        "panel_names": ["status", "journal", "compass", "inventory"][:visible],
        "focus_labels": ["continue", "inventory", "map", "settings",
                         "journal", "help", "quests", "return"][:focus],
        "initial_focus": 0,
        "screen_width": 320 if seed % 2 == 0 else 480,
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "title", "panel_names", "focus_labels", "initial_focus", "screen_width"
    }:
        raise HudActionError("exact source-bound original game HUD required")
    title = layout["title"]
    if type(title) is not str or not 1 <= len(title) <= 100 or any(ord(c) < 32 for c in title):
        raise HudActionError("invalid UI title")
    panels = layout["panel_names"]
    if type(panels) is not list or len(panels) > min(4, config["hud_panels"]):
        raise HudActionError("rendered HUD panel count exceeds source budget")
    allowed = ("status", "journal", "compass", "inventory")
    if len(set(panels)) != len(panels) or any(p not in allowed for p in panels):
        raise HudActionError("unknown or duplicate original HUD widget")
    labels = layout["focus_labels"]
    allowed_labels = ("continue", "inventory", "map", "settings",
                      "journal", "help", "quests", "return")
    if (type(labels) is not list or not 1 <= len(labels) <= min(8, config["focus_targets"])
            or len(set(labels)) != len(labels) or
            any(label not in allowed_labels for label in labels)):
        raise HudActionError("invalid focusable original game controls")
    return {
        "title": title, "panel_names": list(panels),
        "focus_labels": list(labels),
        "initial_focus": _int(layout["initial_focus"], 0, len(labels)-1, "focus"),
        "screen_width": _int(layout["screen_width"], 160, 1920, "width"),
    }


def start(config, seed):
    scene = normalize_layout(config, default_layout(config, seed))
    return {
        "title": scene["title"], "panel_names": list(scene["panel_names"]),
        "focus_labels": list(scene["focus_labels"]),
        "panels_visible": {name: True for name in scene["panel_names"]},
        "focus": scene["initial_focus"], "screen_width": scene["screen_width"],
        "menu_stack": ["root"], "announcements": [], "selected": [],
        "scale": 100, "navigation_steps": 0, "successful_selections": 0,
        "feedback_count": 0, "score": 0, "turn": 0,
        "finished": False, "failed": False, "events": [],
        "real_native_ui_rendered": False,
    }


def apply_scene(state, config, layout):
    if state["turn"]:
        raise HudActionError("cannot change active user interface under player focus")
    new = normalize_layout(config,layout)
    state["title"] = new["title"]
    state["panel_names"] = list(new["panel_names"])
    state["focus_labels"] = list(new["focus_labels"])
    state["panels_visible"] = {name: True for name in new["panel_names"]}
    state["focus"] = new["initial_focus"]
    state["screen_width"] = new["screen_width"]


def step(state, config, action):
    if action not in ACTIONS or state["finished"] or state["failed"]:
        raise HudActionError("unregistered or postterminal HUD control")
    events = []
    if action in ("left", "right", "up", "down"):
        if not config["controller_navigation"]:
            raise HudActionError("controller navigation disabled in authored settings")
        delta = -1 if action in ("left", "up") else 1
        state["focus"] = (state["focus"] + delta) % len(state["focus_labels"])
        state["navigation_steps"] += 1
        state["score"] += 1
        events.append("real_bounded_focus_navigation_applied")
    elif action == "select":
        label = state["focus_labels"][state["focus"]]
        state["selected"].append({
            "control": label, "menu": state["menu_stack"][-1],
            "focus_index": state["focus"],
        })
        state["selected"] = state["selected"][-24:]
        state["successful_selections"] += 1
        state["score"] += 2
        events.append("actual_original_menu_control_activated")
    elif action in ("open:inventory", "open:map"):
        if len(state["menu_stack"]) >= config["menu_depth"]:
            raise HudActionError("menu depth capacity prevents another modal")
        if action[5:] in state["menu_stack"]:
            raise HudActionError("duplicate opened menu would create a focus trap")
        state["menu_stack"].append(action[5:])
        state["focus"] = 0
        events.append("modal_menu_pushed_with_reset_focus")
    elif action == "back":
        if len(state["menu_stack"]) <= 1:
            raise HudActionError("root menu cannot be popped")
        state["menu_stack"].pop()
        state["focus"] = 0
        events.append("modal_menu_popped_to_valid_parent")
    elif action.startswith("toggle:"):
        index = int(action[-1])
        if index >= len(state["panel_names"]):
            raise HudActionError("panel does not exist in reviewed original HUD")
        name = state["panel_names"][index]
        state["panels_visible"][name] = not state["panels_visible"][name]
        events.append("authored_hud_panel_visibility_mutated")
    elif action in ("scale:up", "scale:down"):
        if not config["scalable_text"]:
            raise HudActionError("source disables scalable player text")
        changed = max(75, min(200, state["scale"] + (25 if action == "scale:up" else -25)))
        if changed == state["scale"]:
            raise HudActionError("requested scale exceeds finite player setting range")
        state["scale"] = changed
        events.append("actual_user_text_scale_setting_changed")
    elif action == "hint":
        label = state["focus_labels"][state["focus"]]
        state["announcements"].append("Focus on " + label)
        state["announcements"] = state["announcements"][-24:]
        state["feedback_count"] += 1
        events.append("nonvisual_control_text_cue_generated")
    elif action == "finish":
        if (not state["successful_selections"] or
                not state["feedback_count"] or len(state["menu_stack"]) != 1):
            raise HudActionError("interface trial requires selectable navigation, hint and closed modals")
        state["finished"] = True
        events.append("earned_interactive_hud_walkthrough_completed")
    else:
        events.append("original_game_interface_state_inspected")
    state["turn"] += 1
    state["events"] = events
    return events


__all__ = ["ACTIONS", "HudActionError", "default_layout",
           "normalize_layout", "start", "apply_scene", "step"]
