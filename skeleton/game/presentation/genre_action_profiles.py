"""Source-preserving genre-to-control profiles for historical B024 input actions.

All layouts compile to the *same* remappable semantic ActionMap. Presentation
captures keyboard, mouse, touch and gamepad input; gameplay never handles
device-specific strings. Pure data: no device IO, network or global session.
"""
from __future__ import annotations

from .input_actions import Action, ActionMap, Binding, Control, InputContractError

# Canonical questionnaire genres + #807 vintage racing and sandbox.
GENRE_FAMILY: dict[str, str] = {
    "action-adventure": "adventure", "action": "adventure", "adventure": "adventure",
    "rpg": "rpg", "crpg": "rpg", "jrpg": "rpg", "arpg": "rpg",
    "soulslike": "rpg", "roguelike": "rpg", "roguelite": "rpg",
    "strategy": "strategy", "rts": "strategy", "tactics": "strategy",
    "simulation": "sandbox", "city-builder": "sandbox", "sandbox": "sandbox",
    "platformer": "platformer", "metroidvania": "platformer", "bullet-heaven": "shooter",
    "shooter": "shooter", "fps": "shooter", "battle-royale": "shooter",
    "extraction": "shooter", "survival": "rpg", "horror": "adventure",
    "stealth": "adventure", "immersive-sim": "adventure",
    "fighting": "platformer", "puzzle": "puzzle", "deckbuilder": "puzzle",
    "card": "puzzle", "mmo": "rpg", "mmorpg": "rpg",
    "visual-novel": "adventure", "narrative": "adventure",
    "cozy": "sandbox", "arcade": "platformer", "racing": "racing",
}
FAMILIES = frozenset({"adventure", "rpg", "strategy", "sandbox", "platformer", "shooter", "puzzle", "racing"})


def _bind(action: str, path: str, *, scale: float = 1.0, axis: str = "x", deadzone: float = 0.0) -> Binding:
    return Binding(action, Control.parse(path), scale=scale, axis=axis, deadzone=deadzone)


def _movement() -> list[Binding]:
    return [
        _bind("move", "keyboard:key.w", axis="y"),
        _bind("move", "keyboard:key.s", scale=-1, axis="y"),
        _bind("move", "keyboard:key.a", scale=-1),
        _bind("move", "keyboard:key.d"),
        _bind("move", "gamepad:stick.left.x", deadzone=0.15),
        _bind("move", "gamepad:stick.left.y", axis="y", deadzone=0.15),
        _bind("move", "touch:swipe.x"),
        _bind("move", "touch:swipe.y", axis="y"),
    ]


def genre_action_map(genre: str) -> ActionMap:
    """Build fresh isolated controls per game; a remap never leaks across games."""
    if not isinstance(genre, str) or genre not in GENRE_FAMILY:
        raise InputContractError("unknown genre input profile")
    family = GENRE_FAMILY[genre]
    actions = [Action("pause")]
    binds = [
        _bind("pause", "keyboard:key.escape"),
        _bind("pause", "gamepad:button.start"),
    ]
    if family == "racing":
        actions += [Action("steer", "axis1d"), Action("accelerate", "axis1d"), Action("brake", "axis1d"), Action("boost")]
        binds += [
            _bind("steer", "keyboard:key.a", scale=-1), _bind("steer", "keyboard:key.d"),
            _bind("steer", "gamepad:stick.left.x", deadzone=0.15),
            _bind("steer", "touch:swipe.x"),
            _bind("accelerate", "keyboard:key.w"), _bind("accelerate", "gamepad:trigger.right"),
            _bind("accelerate", "touch:drag.y"),
            _bind("brake", "keyboard:key.s"), _bind("brake", "gamepad:trigger.left"),
            _bind("boost", "keyboard:key.shift"), _bind("boost", "gamepad:button.south"),
            _bind("boost", "touch:double_tap"),
        ]
    else:
        actions.append(Action("move", "axis2d"))
        binds.extend(_movement())
        if family in {"rpg", "shooter", "adventure", "sandbox", "platformer"}:
            actions.append(Action("jump"))
            binds.extend([_bind("jump", "keyboard:key.space"), _bind("jump", "gamepad:button.south")])
        if family in {"adventure", "rpg", "sandbox", "puzzle", "platformer"}:
            actions.append(Action("interact"))
            binds.extend([
                _bind("interact", "keyboard:key.e"),
                _bind("interact", "gamepad:button.east"),
                _bind("interact", "touch:long_press"),
            ])
        if family in {"rpg", "adventure", "platformer"}:
            actions.append(Action("attack"))
            binds.extend([
                _bind("attack", "mouse:button.left"),
                _bind("attack", "gamepad:button.west"),
                _bind("attack", "touch:tap"),
            ])
        if family == "shooter":
            actions += [Action("aim", "axis2d"), Action("fire"), Action("reload")]
            binds += [
                _bind("aim", "mouse:delta.x"), _bind("aim", "mouse:delta.y", axis="y"),
                _bind("aim", "gamepad:stick.right.x", deadzone=0.2),
                _bind("aim", "gamepad:stick.right.y", axis="y", deadzone=0.2),
                _bind("fire", "mouse:button.left"), _bind("fire", "gamepad:trigger.right"),
                _bind("fire", "touch:tap"),
                _bind("reload", "keyboard:key.r"), _bind("reload", "gamepad:button.west"),
            ]
        if family == "puzzle":
            actions += [Action("inspect"), Action("rotate")]
            binds += [
                _bind("inspect", "mouse:button.left"), _bind("inspect", "touch:tap"),
                _bind("rotate", "keyboard:key.r"), _bind("rotate", "gamepad:button.west"),
            ]
        if family == "strategy":
            actions += [Action("select"), Action("command"), Action("build")]
            binds += [
                _bind("select", "mouse:button.left"), _bind("select", "touch:tap"),
                _bind("command", "mouse:button.right"), _bind("command", "touch:double_tap"),
                _bind("build", "keyboard:key.b"), _bind("build", "gamepad:button.north"),
            ]
        if family == "sandbox":
            actions += [Action("build"), Action("craft")]
            binds += [
                _bind("build", "keyboard:key.b"), _bind("build", "gamepad:button.north"),
                _bind("build", "touch:tap"),
                _bind("craft", "keyboard:key.c"), _bind("craft", "gamepad:button.west"),
            ]
    return ActionMap(actions, binds)


def genre_control_profile(genre: str) -> dict[str, object]:
    """JSON-safe bounded descriptor for GameForge questionnaire, tools and UI."""
    m = genre_action_map(genre)
    return {
        "schema": "skeleton.game.genre_action_profile.v1",
        "genre": genre, "family": GENRE_FAMILY[genre],
        "actions": [
            {"id": a.action_id, "kind": a.kind, "context": a.context}
            for a in sorted(m.actions.values(), key=lambda a: a.action_id)
        ],
        "bindings": [
            {"action": b.action_id, "control": str(b.control),
             "modifiers": list(b.modifiers), "scale": b.scale,
             "axis": b.axis, "deadzone": b.deadzone}
            for b in m.bindings()
        ],
    }


__all__ = ["GENRE_FAMILY", "FAMILIES", "genre_action_map", "genre_control_profile"]
