"""Bind an explicitly authored pixel sprite to the ACTUAL Expedition player.

This adapter modifies only the trusted, known anchor of the generated Godot 4
world script; it never interpolates model-supplied code or unbounded strings.
A binding is an original project source record with an explicit dependency on
the chosen sprite. A generated AnimatedSprite3D child follows the real actor's
position on every Expedition move because it is parented to that actor node.
Its native visual correctness still requires running the engine.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import math
import re
from typing import Any

from .studio_interaction_contract import digest

ASSET = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
ANCHOR = "    add_child(actor)\n    _place_actor()"
BINDING_KEYS = frozenset((
    "kind", "target", "asset_id", "animation",
    "pixel_size", "vertical_offset_m", "billboard", "hide_capsule",
))


class SpriteBindingError(ValueError):
    """Model-supplied art cannot be bound to a real native actor."""


def _real(value: Any, name: str, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float):
        raise SpriteBindingError(name + " must be a real finite numeric value")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise SpriteBindingError(name + " exceeds the bounded original world scale")
    return number


def binding_from_source(
    records: Mapping[str, Mapping[str, Any]],
    authored_sprites: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Select at most one reviewed, dependency-bound player visual source."""
    candidates = []
    for record_id, record in sorted(records.items()):
        doc = record.get("document")
        if not isinstance(doc, Mapping) or doc.get("kind") != "sprite_actor_binding":
            continue
        if (record.get("record_id") != record_id
                or record.get("facet") != "scene_forge"
                or set(doc) != BINDING_KEYS):
            raise SpriteBindingError("sprite actor source lacks exact scene-owned fields")
        if doc["target"] != "player_actor":
            raise SpriteBindingError("only the actual Expedition player actor is supported")
        asset, animation = doc["asset_id"], doc["animation"]
        if (type(asset) is not str or ASSET.fullmatch(asset) is None
                or type(animation) is not str or ASSET.fullmatch(animation) is None):
            raise SpriteBindingError("player avatar references unsafe asset or animation")
        if type(doc["billboard"]) is not bool or type(doc["hide_capsule"]) is not bool:
            raise SpriteBindingError("player avatar visual policies must be explicit")
        if len(candidates) >= 1:
            raise SpriteBindingError("multiple original sources compete for player avatar")
        matching = [
            sprite for sprite in authored_sprites
            if sprite.get("asset_id") == asset
        ]
        if len(matching) != 1:
            raise SpriteBindingError("player avatar refers to an unavailable authored sprite")
        selected = matching[0]
        if record.get("depends_on") is None or selected["source_record_id"] not in record["depends_on"]:
            raise SpriteBindingError("sprite actor binding must depend on its real source record")
        if animation not in selected["animation_names"]:
            raise SpriteBindingError("player avatar animation does not exist in original frames")
        candidates.append({
            "schema_version": "skeleton.jeeves.player_sprite_binding.v1",
            "record_id": record_id,
            "asset_id": asset, "animation": animation,
            "target": "player_actor",
            "sprite_source_record_id": selected["source_record_id"],
            "sprite_png_sha256": selected["png_sha256"],
            "sprite_frames_resource_sha256": selected["godot_spriteframes_resource_sha256"],
            "pixel_size": _real(doc["pixel_size"], "visual pixel scaling", 0.001, 0.25),
            "vertical_offset_m": _real(
                doc["vertical_offset_m"], "avatar vertical offset", -10, 30,
            ),
            "billboard": doc["billboard"],
            "hide_capsule": doc["hide_capsule"],
            "engine_actor_visual_execution_verified": False,
        })
    if not candidates:
        return None
    result = candidates[0]
    result["receipt_sha256"] = digest(result)
    return result


def validate_original_avatar_source_graph(
    records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Preflight actual authored player binding before any SQLite revision.

    A source edit that removes or renames a referenced original animation
    cannot leave a previously approved game with a dangling player avatar.
    """
    binding_records = [
        record for record in records.values()
        if isinstance(record.get("document"), Mapping)
        and record["document"].get("kind") == "sprite_actor_binding"
    ]
    if not binding_records:
        return None
    if len(binding_records) != 1:
        raise SpriteBindingError("one and only one source record may own player avatar")
    requested_asset = binding_records[0]["document"].get("asset_id")
    candidates = [
        record for record in records.values()
        if isinstance(record.get("document"), Mapping)
        and record["document"].get("kind") == "pixel_sprite"
        and record["document"].get("asset_id") == requested_asset
    ]
    if len(candidates) != 1:
        raise SpriteBindingError("player avatar requires exactly one original source asset")
    from .studio_sprite_forge import compile_authored_sprite
    from .studio_sprite_godot_resources import (
        compile_godot_sprite_resources, verify_godot_sprite_resources,
    )
    sprite = compile_authored_sprite(candidates[0])
    meta = sprite["metadata"]
    resource = compile_godot_sprite_resources(meta)
    proof = verify_godot_sprite_resources(meta, resource)
    verified = {
        "asset_id": meta["asset_id"],
        "source_record_id": meta["record_id"],
        "png_sha256": meta["png_sha256"],
        "godot_spriteframes_resource_sha256": proof["receipt_sha256"],
        "animation_names": [state["name"] for state in meta["animations"]],
    }
    return binding_from_source(records, [verified])


def bind_sprite_to_expedition_script(
    script: str, binding: Mapping[str, Any],
) -> str:
    """Deterministically inject one reviewed AnimatedSprite3D actor child."""
    if type(script) is not str or script.count(ANCHOR) != 1:
        raise SpriteBindingError("actual Expedition player spawn anchor differs")
    if not isinstance(binding, Mapping):
        raise SpriteBindingError("typed actor visual receipt required")
    without = dict(binding)
    signed = without.pop("receipt_sha256", None)
    if signed != digest(without):
        raise SpriteBindingError("avatar binding source receipt differs")
    asset, animation = binding["asset_id"], binding["animation"]
    if (type(asset) is not str or ASSET.fullmatch(asset) is None
            or type(animation) is not str or ASSET.fullmatch(animation) is None
            or binding["target"] != "player_actor"):
        raise SpriteBindingError("native sprite binding can only target a reviewed actor")
    size = _real(binding["pixel_size"], "pixel size", 0.001, 0.25)
    height = _real(binding["vertical_offset_m"], "vertical offset", -10, 30)
    if type(binding["billboard"]) is not bool or type(binding["hide_capsule"]) is not bool:
        raise SpriteBindingError("actor view policies must be declared booleans")
    builder = [
        "    add_child(actor)",
        "    # Trusted original sprite binding, compiled from the scene forge source.",
        "    var jeeves_frames := load(",
        '        "res://game/frontier/sprites/' + asset + '.tres"',
        "    ) as SpriteFrames",
        '    if jeeves_frames == null or not jeeves_frames.has_animation(&"' + animation + '"):',
        '        push_error("Original player sprite resource or animation missing")',
        "        return",
        "    var jeeves_avatar := AnimatedSprite3D.new()",
        '    jeeves_avatar.name = "OriginalAuthoredAvatar"',
        "    jeeves_avatar.sprite_frames = jeeves_frames",
        '    jeeves_avatar.animation = &"' + animation + '"',
        f"    jeeves_avatar.pixel_size = {size:.8f}",
        f"    jeeves_avatar.position = Vector3(0.0, {height:.6f}, 0.0)",
        "    jeeves_avatar.billboard = BaseMaterial3D.BILLBOARD_ENABLED"
        if binding["billboard"]
        else "    jeeves_avatar.billboard = BaseMaterial3D.BILLBOARD_DISABLED",
        "    actor.add_child(jeeves_avatar)",
        "    jeeves_avatar.play()",
    ]
    if binding["hide_capsule"]:
        # Hiding the actor node hides every descendant too. Clearing its mesh
        # retains its original Node3D transform and animated child visibility.
        builder.append("    actor.mesh = null")
    builder.append("    _place_actor()")
    return script.replace(ANCHOR, "\n".join(builder), 1)


def verify_actor_sprite_binding(
    original_script: str, compiled_script: str, binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild full game script from original trusted engine source bytes."""
    regenerated = bind_sprite_to_expedition_script(original_script, binding)
    if regenerated != compiled_script:
        raise SpriteBindingError("published Godot player visual code differs from source")
    proof = {
        "schema_version": "skeleton.jeeves.player_sprite_binding_compiled.v1",
        "binding_receipt_sha256": binding["receipt_sha256"],
        "base_game_script_sha256": sha256(original_script.encode("utf-8")).hexdigest(),
        "bound_game_script_sha256": sha256(compiled_script.encode("utf-8")).hexdigest(),
        "source_reproduction_verified": True,
        "real_godot_sprite_render_observed": False,
    }
    proof["receipt_sha256"] = digest(proof)
    return proof


__all__ = [
    "SpriteBindingError", "binding_from_source",
    "validate_original_avatar_source_graph",
    "bind_sprite_to_expedition_script", "verify_actor_sprite_binding",
]
