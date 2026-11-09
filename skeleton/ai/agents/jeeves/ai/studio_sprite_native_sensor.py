"""Verified Godot 4 pixel-exact collision sensors for authored player sprites.

The host compiles a bounded, non-blocking Area3D that uses the actual
alpha-mask rectangles for each AnimatedSprite3D frame. The sensor follows
the actual moving player because it is parented under the same actor;
every animation frame changes collision geometry deterministically.

Sensor detection is not full rigid-body blocking. A production physics
body, visual renderer confirmation, and native scene observations are
separate certificates.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from .studio_interaction_contract import digest
from .studio_sprite_hitboxes import verify_exact_sprite_hitboxes
from .studio_sprite_godot_resources import _label

MAX_SHAPES_PER_ACTIVE_FRAME = 128
SCHEMA = "skeleton.jeeves.godot_alpha_sensor.v1"


class SpriteSensorError(ValueError):
    """Frame-accurate native collision sensor cannot be verified safely."""


_SENSOR_SCRIPT = r'''extends Area3D
# Source-owned area sensor; never claims blocking-body contact physics.
const SPRITE_META = "res://game/frontier/sprites/ASSET_ID.json"
const HITBOX_META = "res://game/frontier/sprites/ASSET_ID.hitboxes.json"
const MAX_SHAPES = 128
const SENSOR_THICKNESS_M = 0.06
var avatar: AnimatedSprite3D
var animation_frames: Dictionary = {}
var rectangles_by_id: Dictionary = {}
var sensor_shapes: Array[CollisionShape3D] = []
var pixel_size_m: float = 0.0

func _read_json(path: String) -> Dictionary:
    if not FileAccess.file_exists(path):
        push_error("Original sprite collision source is missing: " + path)
        return {}
    var reader := FileAccess.open(path, FileAccess.READ)
    if reader == null or reader.get_length() > 1048576:
        push_error("Original collision manifest cannot be read inside budget")
        return {}
    var parsed = JSON.parse_string(reader.get_as_text())
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Original collision manifest requires typed JSON")
        return {}
    return parsed

func _ready() -> void:
    collision_layer = 2
    collision_mask = 1
    monitoring = true
    monitorable = true
    avatar = get_parent().get_node_or_null("OriginalAuthoredAvatar") as AnimatedSprite3D
    if avatar == null:
        push_error("Original sprite sensor has no player animation")
        return
    var metadata := _read_json(SPRITE_META)
    var hitboxes := _read_json(HITBOX_META)
    if (str(metadata.get("asset_id", "")) != "ASSET_ID"
            or str(hitboxes.get("asset_id", "")) != "ASSET_ID"
            or typeof(metadata.get("animations", null)) != TYPE_ARRAY
            or typeof(hitboxes.get("frames", null)) != TYPE_ARRAY):
        push_error("Authored collision manifest or original sprite identity differs")
        return
    pixel_size_m = avatar.pixel_size
    var authored_frames: Array = metadata.get("frames", [])
    var collision_frames: Array = hitboxes.get("frames", [])
    if (authored_frames.is_empty() or authored_frames.size() > 64
            or authored_frames.size() != collision_frames.size()):
        push_error("Original frame count conflicts with collision proof")
        return
    var first_frame = authored_frames[0]
    var pivot = first_frame.get("pivot_px", [])
    if typeof(pivot) != TYPE_ARRAY or pivot.size() != 2:
        push_error("Original collision frame lacks authored pixel pivot")
        return
    var frame_w = int(metadata.get("frame_width_px", 0))
    var frame_h = int(metadata.get("frame_height_px", 0))
    if frame_w <= 0 or frame_h <= 0:
        push_error("Source sprite dimensions are not valid")
        return
    avatar.offset = Vector2(
        float(frame_w) * 0.5 - float(pivot[0]),
        float(frame_h) * 0.5 - float(pivot[1])
    )
    for frame in collision_frames:
        var name = str(frame.get("frame_id", ""))
        if name.is_empty() or rectangles_by_id.has(name):
            push_error("Original collision frame name is invalid")
            return
        var blocks = frame.get("sprite_local_scaled_rects", [])
        if typeof(blocks) != TYPE_ARRAY or blocks.size() > MAX_SHAPES:
            push_error("Original alpha-mask collision budget exceeded")
            return
        rectangles_by_id[name] = blocks
    for state in metadata["animations"]:
        var name = str(state.get("name", ""))
        var refs = state.get("frame_ids", [])
        if name.is_empty() or typeof(refs) != TYPE_ARRAY:
            push_error("Original animation collision sequence is invalid")
            return
        for ref in refs:
            if not rectangles_by_id.has(str(ref)):
                push_error("Animation references unavailable source collision frame")
                return
        animation_frames[name] = refs
    avatar.frame_changed.connect(_update_exact_alpha_sensor)
    avatar.animation_changed.connect(_update_exact_alpha_sensor)
    _update_exact_alpha_sensor()

func _update_exact_alpha_sensor() -> void:
    if avatar == null or pixel_size_m <= 0:
        return
    var keys = animation_frames.get(str(avatar.animation), [])
    var index = avatar.frame
    if typeof(keys) != TYPE_ARRAY or index < 0 or index >= keys.size():
        _deactivate_all()
        return
    var boxes = rectangles_by_id.get(str(keys[index]), [])
    if typeof(boxes) != TYPE_ARRAY or boxes.size() > MAX_SHAPES:
        _deactivate_all()
        push_error("Sprite collision frame exceeded native shape budget")
        return
    while sensor_shapes.size() < boxes.size():
        var collision := CollisionShape3D.new()
        collision.name = "OriginalPixelAlphaRect"
        add_child(collision)
        sensor_shapes.append(collision)
    for i in range(sensor_shapes.size()):
        var collision = sensor_shapes[i]
        if i >= boxes.size():
            collision.disabled = true
            continue
        var rect = boxes[i]
        if (typeof(rect) != TYPE_ARRAY or rect.size() != 4
                or float(rect[2]) <= 0 or float(rect[3]) <= 0):
            _deactivate_all()
            push_error("Original sprite collision has invalid rectangle")
            return
        var shape := BoxShape3D.new()
        shape.size = Vector3(
            float(rect[2]) * pixel_size_m,
            float(rect[3]) * pixel_size_m,
            SENSOR_THICKNESS_M
        )
        collision.shape = shape
        collision.position = Vector3(
            (float(rect[0]) + float(rect[2]) * 0.5) * pixel_size_m,
            -(float(rect[1]) + float(rect[3]) * 0.5) * pixel_size_m,
            0.0
        )
        collision.disabled = false

func _deactivate_all() -> void:
    for sensor in sensor_shapes:
        sensor.disabled = true
'''


def compile_sprite_sensor_source(
    metadata: Mapping[str, Any],
    hitboxes: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a genuine native Area3D script from verified sprite mask data."""
    verified = verify_exact_sprite_hitboxes(metadata, hitboxes)
    asset = _label(metadata.get("asset_id"), "original sprite sensor resource")
    if not isinstance(metadata.get("frames"), list):
        raise SpriteSensorError("sprite metadata lacks original frames")
    for item in verified["frames"]:
        if item["rectangle_count"] > MAX_SHAPES_PER_ACTIVE_FRAME:
            raise SpriteSensorError(
                "authored sprite exceeds real-time collision node budget"
            )
    output = _SENSOR_SCRIPT.replace("ASSET_ID", asset)
    evidence = {
        "schema_version": SCHEMA,
        "asset_id": asset,
        "sprite_metadata_sha256": metadata["receipt_sha256"],
        "source_hitbox_receipt_sha256": verified["receipt_sha256"],
        "sensor_script_sha256": sha256(output.encode("utf-8")).hexdigest(),
        "sensor_max_shapes_per_frame": MAX_SHAPES_PER_ACTIVE_FRAME,
        "runtime_collision_type": "Area3D_overlap_sensor",
        "blocking_rigidbody_collision_claimed": False,
        "native_godot_collision_test_executed": False,
    }
    evidence["receipt_sha256"] = digest(evidence)
    return {"script": output, "receipt": evidence}


def verify_sprite_sensor_source(
    metadata: Mapping[str, Any],
    hitboxes: Mapping[str, Any],
    source: str, receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently reproduce every native-script byte and source claim."""
    expected = compile_sprite_sensor_source(metadata, hitboxes)
    if source != expected["script"] or not isinstance(receipt, Mapping) or dict(receipt) != expected["receipt"]:
        raise SpriteSensorError("native pixel collision sensor differs from authored source")
    return expected["receipt"]


__all__ = [
    "SpriteSensorError", "compile_sprite_sensor_source",
    "verify_sprite_sensor_source",
]
