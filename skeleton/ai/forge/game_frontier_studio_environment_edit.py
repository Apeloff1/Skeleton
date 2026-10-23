"""Fifteen genuine RPG environment-page editor commands for Forge Studio.

Every command creates a new validated StudioProject; the existing deterministic
RPG evaluator consumes the resulting conditions, flags, priorities and actions.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .game_frontier_studio import StudioError, StudioProject
from .game_frontier_rpg_events import (
    EnvironmentalTrigger, RPGEventAction, RPGEventPage,
)
from .game_frontier_studio_map_edit import _integer, _name

ENV_ACTIONS = (
    "environment_page_add", "environment_page_remove", "environment_page_clone",
    "environment_page_priority", "environment_page_enable",
    "environment_page_repeat", "environment_page_cooldown",
    "environment_condition_add", "environment_condition_edit",
    "environment_condition_remove", "environment_action_add",
    "environment_action_edit", "environment_action_remove",
    "environment_flag_require", "environment_flag_clear",
)


def _page(project: StudioProject, args: Mapping[str, Any]):
    key = _name(args, "page_id")
    for index, page in enumerate(project.environmental_pages):
        if page.page_id == key:
            return index, page
    raise StudioError("environment page not found")


def _replace(items: tuple, index: int, value):
    return items[:index] + (value,) + items[index + 1:]


def _finite(args: Mapping[str, Any], field: str, default=None) -> float:
    import math
    value = args.get(field, default)
    if type(value) not in (float, int) or not math.isfinite(value) or abs(value) > 1e10:
        raise StudioError(f"{field} must be finite and bounded")
    return float(value)


def _trigger(args: Mapping[str, Any]) -> EnvironmentalTrigger:
    signal = args.get("signal")
    comparison = args.get("comparison", "at_least")
    if type(signal) is not str or type(comparison) is not str:
        raise StudioError("environment needs a typed sensor comparator")
    upper = args.get("upper_threshold")
    return EnvironmentalTrigger(
        signal, comparison, _finite(args, "threshold"),
        _finite(args, "upper_threshold") if upper is not None else None,
        _finite(args, "hysteresis", 0),
    )


def _action(args: Mapping[str, Any]) -> RPGEventAction:
    kind = args.get("kind")
    channel = args.get("channel")
    target = args.get("target")
    value = args.get("value", "")
    if any(type(v) is not str for v in (kind, channel, target, value)):
        raise StudioError("environment action requires typed kind/channel/target/value")
    return RPGEventAction(kind, channel, target, value)


def edit_environment(project: StudioProject, operation: str,
                     args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project, StudioProject) or operation not in ENV_ACTIONS or not isinstance(args, Mapping):
        raise StudioError("invalid environment editor command")
    if operation == "environment_page_add":
        ident = _name(args, "page_id")
        if ident in {p.page_id for p in project.environmental_pages} | {e.event_id for e in project.events}:
            raise StudioError("environment identity already authored")
        cond = _trigger(args)
        action = _action(args)
        page = RPGEventPage(ident, 0, (cond,), (action,))
        return replace(project, environmental_pages=project.environmental_pages + (page,))
    index, page = _page(project, args)
    if operation == "environment_page_remove":
        return replace(project, environmental_pages=project.environmental_pages[:index] +
                       project.environmental_pages[index + 1:])
    if operation == "environment_page_clone":
        name = _name(args, "new_page_id")
        if name in {p.page_id for p in project.environmental_pages} | {e.event_id for e in project.events}:
            raise StudioError("duplicated environment page ID")
        return replace(project, environmental_pages=project.environmental_pages +
                       (replace(page, page_id=name),))
    if operation == "environment_page_priority":
        page = replace(page, priority=_integer(args, "priority", -100, 100))
    elif operation in ("environment_page_enable", "environment_page_repeat"):
        enabled = args.get("enabled") if operation.endswith("enable") else args.get("repeat")
        if type(enabled) is not bool:
            raise StudioError("environment switch must be boolean")
        page = replace(page, **({"enabled": enabled}
                                if operation.endswith("enable") else {"repeat": enabled}))
    elif operation == "environment_page_cooldown":
        page = replace(page, cooldown_ms=_integer(args, "cooldown_ms", 0, 86400000))
    elif operation.startswith("environment_condition_"):
        if operation == "environment_condition_add":
            if len(page.conditions) >= 32:
                raise StudioError("environment condition capacity reached")
            page = replace(page, conditions=page.conditions + (_trigger(args),))
        else:
            position = _integer(args, "index", 0, len(page.conditions) - 1)
            if operation == "environment_condition_remove":
                if len(page.conditions) == 1:
                    raise StudioError("RPG event must retain an actual condition")
                page = replace(page, conditions=page.conditions[:position] +
                               page.conditions[position + 1:])
            else:
                page = replace(page, conditions=_replace(page.conditions, position, _trigger(args)))
    elif operation.startswith("environment_action_"):
        if operation == "environment_action_add":
            if len(page.actions) >= 32:
                raise StudioError("RPG event has too many actions")
            page = replace(page, actions=page.actions + (_action(args),))
        else:
            position = _integer(args, "index", 0, len(page.actions) - 1)
            if operation == "environment_action_remove":
                if len(page.actions) == 1:
                    raise StudioError("RPG event must retain an executable action")
                page = replace(page, actions=page.actions[:position] + page.actions[position + 1:])
            else:
                page = replace(page, actions=_replace(page.actions, position, _action(args)))
    elif operation == "environment_flag_require":
        name = _name(args, "flag")
        value = args.get("required")
        if type(value) is not bool:
            raise StudioError("environment required flag must be boolean")
        flags = {key: state for key, state in page.required_flags}
        flags[name] = value
        page = replace(page, required_flags=tuple(sorted(flags.items())))
    elif operation == "environment_flag_clear":
        name = _name(args, "flag")
        if name not in dict(page.required_flags):
            raise StudioError("flag is not required by this environment event")
        page = replace(page, required_flags=tuple(
            (key, flag) for key, flag in page.required_flags if key != name))
    return replace(project, environmental_pages=_replace(project.environmental_pages, index, page))
