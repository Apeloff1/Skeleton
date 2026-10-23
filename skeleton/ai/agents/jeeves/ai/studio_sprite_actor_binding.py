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
BINDING_OPTIONAL = frozenset((
    "movement_animations", "collision_sensor", "directional_animations",
    "audio_cue_bindings",
))
TRAVEL_STAMINA_ANCHOR = """    stamina -= int(costs["stamina"])"""


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
    authored_audio: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Select at most one reviewed, dependency-bound player visual source."""
    candidates = []
    for record_id, record in sorted(records.items()):
        doc = record.get("document")
        if not isinstance(doc, Mapping) or doc.get("kind") != "sprite_actor_binding":
            continue
        if (record.get("record_id") != record_id
                or record.get("facet") != "scene_forge"
                or not BINDING_KEYS <= set(doc) <= BINDING_KEYS | BINDING_OPTIONAL):
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
        from .studio_sprite_direction import validate_directional_animations
        directions = doc.get("directional_animations", {})
        if directions:
            directions = validate_directional_animations(
                directions, available=selected["animation_names"],
                default=animation,
            )
        elif not isinstance(directions, dict):
            raise SpriteBindingError("directional heading map must be an object")
        collision_sensor = doc.get("collision_sensor", False)
        if type(collision_sensor) is not bool:
            raise SpriteBindingError("native alpha sensor policy must be an explicit boolean")
        movement_animations = doc.get("movement_animations", {})
        if (not isinstance(movement_animations, dict)
                or len(movement_animations) > 32
                or any(
                    type(mode) is not str or ASSET.fullmatch(mode) is None
                    or type(name) is not str or name not in selected["animation_names"]
                    for mode, name in movement_animations.items()
                )):
            raise SpriteBindingError(
                "movement state map must reference actual original animation names"
            )
        cues = doc.get("audio_cue_bindings", {})
        if (not isinstance(cues, dict) or len(cues) > 32):
            raise SpriteBindingError("original cue audio mapping must be a finite typed object")
        available_cues = selected.get("frame_cue_event_ids", [])
        if not isinstance(available_cues, list):
            raise SpriteBindingError("reviewed sprite frame cue catalogue is missing")
        catalog = {item["asset_id"]: item for item in (authored_audio or [])}
        if len(catalog) != len(authored_audio or []):
            raise SpriteBindingError("original audio asset identities are ambiguous")
        audio_refs: dict[str, str] = {}
        for event_id, sound_asset in sorted(cues.items()):
            if (type(event_id) is not str or ASSET.fullmatch(event_id) is None
                    or event_id not in available_cues
                    or type(sound_asset) is not str
                    or ASSET.fullmatch(sound_asset) is None):
                raise SpriteBindingError(
                    "audio effect cue must reference an authored sprite event and sound"
                )
            original = catalog.get(sound_asset)
            if original is None or original["source_record_id"] not in record["depends_on"]:
                raise SpriteBindingError(
                    "audio cue requires real reviewed sound and exact original dependency"
                )
            audio_refs[event_id] = original["source_sha256"]
        if audio_refs and selected.get("frame_cues_sha256") is None:
            raise SpriteBindingError("audio output cannot play without authored frame signals")
        candidates.append({
            "audio_cue_bindings": {
                cue: cues[cue] for cue in sorted(cues)
            },
            "audio_source_sha256_by_event": audio_refs,
            "schema_version": "skeleton.jeeves.player_sprite_binding.v1",
            "collision_sensor": collision_sensor,
            "directional_animations": {
                key: directions[key] for key in sorted(directions)
            },
            "movement_animations": {
                key: movement_animations[key]
                for key in sorted(movement_animations)
            },
            "record_id": record_id,
            "asset_id": asset, "animation": animation,
            "target": "player_actor",
            "sprite_source_record_id": selected["source_record_id"],
            "sprite_png_sha256": selected["png_sha256"],
            "sprite_frames_resource_sha256": selected["godot_spriteframes_resource_sha256"],
            "frame_cues_sha256": selected.get("frame_cues_sha256"),
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
        "frame_cues_sha256": (
            meta["frame_cues"]["receipt_sha256"] if meta.get("frame_cues")
            else None
        ),
        "animation_names": [state["name"] for state in meta["animations"]],
    }
    from .studio_original_audio import compile_original_sound_collection
    verified["frame_cue_event_ids"] = (
        [cue["event_id"] for cue in meta["frame_cues"]["cues"]]
        if meta.get("frame_cues") else []
    )
    authored_audio = [
        {
            "asset_id": sound["metadata"]["asset_id"],
            "source_record_id": sound["metadata"]["source_record_id"],
            "source_sha256": sound["metadata"]["source_sha256"],
        }
        for sound in compile_original_sound_collection(records)["assets"]
    ]
    return binding_from_source(records, [verified], authored_audio)


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
    ]
    audio_cues = binding.get("audio_cue_bindings", {})
    if (not isinstance(audio_cues, dict) or len(audio_cues) > 32
            or any(type(key) is not str or ASSET.fullmatch(key) is None
                   or type(value) is not str or ASSET.fullmatch(value) is None
                   for key, value in audio_cues.items())):
        raise SpriteBindingError("native audio cue routing lost original review")
    if audio_cues and binding.get("frame_cues_sha256") is None:
        raise SpriteBindingError("sound playback requires authored cue signal source")
    if audio_cues:
        verified_shas = binding.get("audio_source_sha256_by_event")
        if (not isinstance(verified_shas, dict)
                or set(verified_shas) != set(audio_cues)
                or any(type(digest_value) is not str or len(digest_value) != 64
                       or any(ch not in "0123456789abcdef" for ch in digest_value)
                       for digest_value in verified_shas.values())):
            raise SpriteBindingError("original sound source lineage is incomplete")
    if binding.get("frame_cues_sha256") is not None:
        cue_digest = binding["frame_cues_sha256"]
        if (type(cue_digest) is not str or len(cue_digest) != 64
                or any(c not in "0123456789abcdef" for c in cue_digest)):
            raise SpriteBindingError("animation cue receipt must have original SHA-256")
        builder.extend([
            "    # Godot cue script only emits source-authorized frame signals.",
            "    var jeeves_cue_logic := load(",
            '        "res://game/frontier/sprites/' + asset + '.cues.gd"',
            "    ) as Script",
            "    if jeeves_cue_logic == null:",
            '        push_error("Authored sprite frame-cue signals are missing")',
            "        return",
            "    jeeves_avatar.set_script(jeeves_cue_logic)",
        ])
    if audio_cues:
        # Only reviewed event and sound identities become code literals.
        # No arbitrary user-provided expression, path or script is evaluated.
        entries = ", ".join(
            f'"{event_id}": "{audio_cues[event_id]}"'
            for event_id in sorted(audio_cues)
        )
        builder.extend([
            "    var jeeves_sound_player := AudioStreamPlayer3D.new()",
            '    jeeves_sound_player.name = "OriginalCueAudioPlayer"',
            "    actor.add_child(jeeves_sound_player)",
            "    var jeeves_cue_to_sound: Dictionary = {" + entries + "}",
            '    jeeves_avatar.connect("cue_fired", func(event_id, _category, _name, _frame):',
            "        var jeeves_sound_id := str(jeeves_cue_to_sound.get(str(event_id), \"\"))",
            '        if jeeves_sound_id != "":',
            '            var jeeves_original_wav := load(',
            '                "res://game/frontier/audio/" + jeeves_sound_id + ".wav"',
            '            ) as AudioStream',
            "            if jeeves_original_wav != null:",
            "                jeeves_sound_player.stream = jeeves_original_wav",
            "                jeeves_sound_player.play()",
            "    )",
        ])
    builder.extend([
        "    actor.add_child(jeeves_avatar)",
        "    jeeves_avatar.play()",
    ])
    if binding.get("collision_sensor", False) is True:
        builder.extend([
            "    # Explicit Area3D nonblocking sprite-alpha collision sensor.",
            "    var jeeves_sensor := Area3D.new()",
            '    jeeves_sensor.name = "OriginalAlphaCollisionSensor"',
            "    jeeves_sensor.set_script(load(",
            '        "res://game/frontier/sprites/' + asset + '.sensor.gd"',
            "    ))",
            "    actor.add_child(jeeves_sensor)",
        ])
    elif binding.get("collision_sensor", False) is not False:
        raise SpriteBindingError("native alpha collision policy was modified")
    if binding["hide_capsule"]:
        # Hiding the actor node hides every descendant too. Clearing its mesh
        # retains its original Node3D transform and animated child visibility.
        builder.append("    actor.mesh = null")
    builder.append("    _place_actor()")
    compiled = script.replace(ANCHOR, "\n".join(builder), 1)
    movement = binding.get("movement_animations", {})
    if (not isinstance(movement, dict) or len(movement) > 32
            or any(type(mode) is not str or ASSET.fullmatch(mode) is None
                   or type(name) is not str or ASSET.fullmatch(name) is None
                   for mode, name in movement.items())):
        raise SpriteBindingError("native avatar movement map lost source identity")
    if movement:
        if compiled.count(TRAVEL_STAMINA_ANCHOR) != 1:
            raise SpriteBindingError("trusted native travel transition anchor changed")
        # This executes only after Godot's already authoritative travel budget
        # and lock checks have succeeded, not when a blocked action is proposed.
        entries = ", ".join(
            f'"{mode}": "{movement[mode]}"' for mode in sorted(movement)
        )
        travel_logic = [
            '    var jeeves_avatar_node := actor.get_node_or_null("OriginalAuthoredAvatar")',
            "    if jeeves_avatar_node is AnimatedSprite3D:",
            '        var jeeves_travel_animations: Dictionary = {' + entries + '}',
            '        var jeeves_travel_mode := str(edge.get("mode", ""))',
            '        var jeeves_animation := str(',
            '            jeeves_travel_animations.get(jeeves_travel_mode, "' + animation + '")',
            "        )",
            "        if jeeves_avatar_node.sprite_frames.has_animation(jeeves_animation):",
            "            jeeves_avatar_node.play(jeeves_animation)",
            TRAVEL_STAMINA_ANCHOR,
        ]
        compiled = compiled.replace(
            TRAVEL_STAMINA_ANCHOR, "\n".join(travel_logic), 1,
        )
    return compiled


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
