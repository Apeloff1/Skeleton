"""Eight-way world-space facing for a REAL Godot AnimatedSprite3D actor.

This optional sprite direction compiler alters only the known Expedition
`_place_actor` anchor. Heading comes from the real previous/new waypoint
positions on the horizontal XZ plane, not a generated placeholder direction.
The model never provides executable source; it provides reviewed direction
identifiers pointing to previously authored and compiled sprite animations.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import re
from typing import Any

from .studio_interaction_contract import digest

FACING = (
    "north", "north_east", "east", "south_east",
    "south", "south_west", "west", "north_west",
)
ANIMATION_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
PLACE_ANCHOR = (
    "func _place_actor() -> void:\n"
    "    actor.position = _where(waypoint_by_id[current_id]) + Vector3(0, 3, 0)"
)


class SpriteDirectionError(ValueError):
    """A direction lacks an authored animation or the world spawn has drifted."""


def validate_directional_animations(
    directions: Any, *, available: list[str], default: str,
) -> dict[str, str]:
    """Require explicit, existing animations for each authored compass heading."""
    if (not isinstance(directions, dict) or not 1 <= len(directions) <= 8
            or type(default) is not str or default not in available):
        raise SpriteDirectionError(
            "directional sprites require authored headings and a real default animation"
        )
    if (not isinstance(available, list) or not available
            or len(available) != len(set(available))):
        raise SpriteDirectionError("compiled source animation identity is ambiguous")
    output: dict[str, str] = {}
    for facing, animation in sorted(directions.items()):
        if (type(facing) is not str or facing not in FACING
                or type(animation) is not str
                or ANIMATION_ID.fullmatch(animation) is None
                or animation not in available):
            raise SpriteDirectionError(
                "compass direction references an uncompiled sprite animation"
            )
        output[facing] = animation
    return output


def compile_eight_way_actor_facing(
    original_script: str, binding: Mapping[str, Any],
) -> str:
    """Inject compass selection once; leave gameplay, stamina, routes intact."""
    if (type(original_script) is not str
            or original_script.count(PLACE_ANCHOR) != 1):
        raise SpriteDirectionError("real Godot actor placement anchor changed")
    if not isinstance(binding, Mapping):
        raise SpriteDirectionError("source-bound avatar declaration required")
    content = dict(binding)
    signed = content.pop("receipt_sha256", None)
    if signed != digest(content):
        raise SpriteDirectionError("actor source receipt differs from original")
    directions = binding.get("directional_animations", {})
    if not isinstance(directions, dict) or not directions:
        raise SpriteDirectionError("directional compiler requires authored headings")
    if any(
        facing not in FACING
        or type(animation) is not str
        or ANIMATION_ID.fullmatch(animation) is None
        for facing, animation in directions.items()
    ):
        raise SpriteDirectionError("native compass direction identity was altered")
    pairs = ", ".join(
        f'"{direction}": "{directions[direction]}"'
        for direction in sorted(directions)
    )
    compass = ", ".join('"' + value + '"' for value in FACING)
    injected = "\n".join([
        "func _place_actor() -> void:",
        "    # Native compass uses horizontal travel, never vertical lift/drop.",
        "    var jeeves_old_actor_position := actor.position",
        "    actor.position = _where(waypoint_by_id[current_id]) + Vector3(0, 3, 0)",
        '    var jeeves_heading_avatar := actor.get_node_or_null("OriginalAuthoredAvatar")',
        "    if jeeves_heading_avatar is AnimatedSprite3D:",
        "        var jeeves_compass_delta := actor.position - jeeves_old_actor_position",
        "        jeeves_compass_delta.y = 0.0",
        "        if jeeves_compass_delta.length_squared() > 0.000001:",
        "            var jeeves_compass_names: Array = [" + compass + "]",
        "            var jeeves_facing := posmod(",
        "                int(round(atan2(jeeves_compass_delta.x, -jeeves_compass_delta.z)",
        "                    / (PI / 4.0))), 8",
        "            )",
        "            var jeeves_current_heading: String = jeeves_compass_names[jeeves_facing]",
        "            var jeeves_authored_headings: Dictionary = {" + pairs + "}",
        "            if jeeves_authored_headings.has(jeeves_current_heading):",
        "                var jeeves_animation_name: String = str(",
        "                    jeeves_authored_headings[jeeves_current_heading]",
        "                )",
        "                if jeeves_heading_avatar.sprite_frames.has_animation(",
        "                    jeeves_animation_name",
        "                ):",
        "                    jeeves_heading_avatar.play(jeeves_animation_name)",
    ])
    return original_script.replace(PLACE_ANCHOR, injected, 1)


def verify_eight_way_actor_facing(
    original_script: str, result_script: str, binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct all modified GDScript bytes under independent source proof."""
    regenerated = compile_eight_way_actor_facing(original_script, binding)
    if regenerated != result_script:
        raise SpriteDirectionError("actual player heading GDScript changed after compilation")
    body = {
        "schema_version": "skeleton.jeeves.actor_compass_sprite.v1",
        "source_binding_sha256": binding["receipt_sha256"],
        "original_engine_source_sha256": sha256(
            original_script.encode("utf-8")
        ).hexdigest(),
        "compass_bound_engine_source_sha256": sha256(
            result_script.encode("utf-8")
        ).hexdigest(),
        "north_reference": "negative_world_z",
        "east_reference": "positive_world_x",
        "vertical_movement_affects_facing": False,
        "headings_recompiled": sorted(binding["directional_animations"]),
        "engine_compass_observed": False,
    }
    body["receipt_sha256"] = digest(body)
    return body


__all__ = [
    "SpriteDirectionError", "FACING", "validate_directional_animations",
    "compile_eight_way_actor_facing", "verify_eight_way_actor_facing",
]
