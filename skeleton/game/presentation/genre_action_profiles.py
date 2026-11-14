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
# These 67 IDs are the *existing* Galaxy Studio fallback catalogue, not an
# invented set of gameplay archetypes. Eight families govern input layout only;
# each game keeps its original genre ID and independent mechanics pipeline.
GALAXY_GENRE_FAMILY: dict[str, str] = {
    "platformer_2d": "platformer", "platformer_3d": "platformer",
    "rpg": "rpg", "fps": "shooter", "tps": "shooter",
    "battle_royale": "shooter", "mmorpg": "rpg", "moba": "strategy",
    "puzzle": "puzzle", "strategy_rts": "strategy", "turn_based_strategy": "strategy",
    "four_x": "strategy", "grand_strategy": "strategy", "colony_sim": "sandbox",
    "automation": "sandbox", "survival": "sandbox", "soulslike": "rpg",
    "metroidvania": "platformer", "roguelike": "rpg", "deckbuilder": "puzzle",
    "fighting": "platformer", "racing": "racing", "horror": "adventure",
    "stealth": "adventure", "simulation": "sandbox", "city_builder": "sandbox",
    "farming_sim": "sandbox", "sandbox": "sandbox", "visual_novel": "adventure",
    "rhythm": "puzzle", "tower_defense": "strategy", "sports": "racing",
    "extraction_shooter": "shooter", "social_deduction": "adventure",
    "idle_clicker": "sandbox", "gacha": "rpg", "space_sim": "sandbox",
    "flight_sim": "racing", "naval_pirate": "adventure", "party_game": "platformer",
    "educational": "puzzle", "cozy_game": "sandbox", "hunting": "adventure",
    "fishing": "sandbox", "mech_robot": "shooter", "bullet_hell": "shooter",
    "walking_sim": "adventure", "point_and_click": "puzzle",
    "auto_battler": "strategy", "dating_sim": "adventure",
    "vehicle_combat": "shooter", "immersive_sim": "adventure",
    "tycoon": "sandbox", "management_sim": "sandbox", "mmo": "rpg",
    "action_adventure": "adventure", "open_world": "adventure",
    "looter_shooter": "shooter", "extraction_rpg": "rpg", "card_game": "puzzle",
    "board_game": "puzzle", "text_adventure": "adventure",
    "roguelite_shooter": "shooter", "twin_stick": "shooter",
    "stealth_action": "adventure", "tactics": "strategy",
    "metaverse_social": "sandbox",
}
# Canonical questionnaire genres take precedence for shared spellings.
QUESTIONNAIRE_GENRE_FAMILY = dict(GENRE_FAMILY)
GENRE_FAMILY = {**GALAXY_GENRE_FAMILY, **QUESTIONNAIRE_GENRE_FAMILY}

# Historical authored mappings remain authoritative. Complete the 158-label
# GameForge *semantic input* taxonomy with safe group defaults only.
# This is not a promise of 158 playable engines.
from skeleton.context.genre_catalog import GENRE_GROUPS, GENRE_ERA_VOTES

_GROUP_CONTROL_FAMILY = {
    "action-shooting": "shooter", "role-playing": "rpg",
    "strategy-tactics": "strategy", "simulation-management": "sandbox",
    "adventure-narrative": "adventure", "platform-exploration": "adventure",
    "puzzle-tabletop": "puzzle", "horror-suspense": "adventure",
    "racing-sports": "racing", "creative-social": "sandbox",
    "arcade-casual": "platformer",
}
for _group in GENRE_GROUPS:
    for _genre, _era in _group["genres"]:
        GENRE_FAMILY.setdefault(_genre, _GROUP_CONTROL_FAMILY[_group["id"]])

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
        # Native/replay compatibility: discrete D-pad routes can enter the
        # canonical input router; raw analog sticks require a separate adapter.
        _bind("move", "gamepad:button.dpad_up", axis="y"),
        _bind("move", "gamepad:button.dpad_down", scale=-1, axis="y"),
        _bind("move", "gamepad:button.dpad_left", scale=-1),
        _bind("move", "gamepad:button.dpad_right"),
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
        "catalogs": sorted([name for name, present in (
            ("galaxy", genre in GALAXY_GENRE_FAMILY),
            ("gameforge", genre in QUESTIONNAIRE_GENRE_FAMILY),
            ("gameforge-extended", genre in GENRE_ERA_VOTES),
        ) if present]),
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


__all__ = ["GENRE_FAMILY", "GALAXY_GENRE_FAMILY", "QUESTIONNAIRE_GENRE_FAMILY", "FAMILIES", "genre_action_map", "genre_control_profile"]
