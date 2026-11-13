"""Authored frame-accurate cues, bound to original sprite animation timing.

Cues are immutable signal metadata, not executable commands. They may
represent audio, VFX, impacts or footfalls, but the emitter deliberately grants
no audio/file/scene/physics access. Only a separately approved game consumer
can connect the emitted Godot signals to an actual effect.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import re
from typing import Any

from .studio_interaction_contract import digest

IDENTITY = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
CATEGORIES = frozenset((
    "footstep", "impact", "attack", "sound", "vfx", "interaction", "marker",
))
MAX_CUES = 128
SCHEMA = "skeleton.jeeves.sprite_frame_cues.v1"


class SpriteCueError(ValueError):
    """An animation cue cannot be supported by reviewed source frames."""


def _id(value: Any, label: str) -> str:
    if type(value) is not str or IDENTITY.fullmatch(value) is None:
        raise SpriteCueError(label + " must be a safe, portable identifier")
    return value


def compile_frame_cues(
    source: Mapping[str, Any], animations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Compile explicit authored frame triggers, never infer missing events."""
    if "cues" not in source:
        return None
    authored = source["cues"]
    if type(authored) is not list or not 1 <= len(authored) <= MAX_CUES:
        raise SpriteCueError("frame cues require 1..128 original authored entries")
    states = {item["name"]: item for item in animations}
    if len(states) != len(animations):
        raise SpriteCueError("animation names are not unique")
    used: set[tuple[str, int, str]] = set()
    output: list[dict[str, Any]] = []
    for entry in authored:
        if not isinstance(entry, dict) or set(entry) != {
            "animation", "frame_index", "event_id", "category",
        }:
            raise SpriteCueError("cue must declare animation, frame_index, event_id and category")
        state = _id(entry["animation"], "cue animation")
        event_id = _id(entry["event_id"], "cue event")
        category = entry["category"]
        if type(category) is not str or category not in CATEGORIES:
            raise SpriteCueError("cue category is outside the non-executing signal vocabulary")
        index = entry["frame_index"]
        if (state not in states or type(index) is not int
                or not 0 <= index < len(states[state]["frame_ids"])):
            raise SpriteCueError("cue refers to an animation or frame that was not authored")
        key = (state, index, event_id)
        if key in used:
            raise SpriteCueError("duplicate cue identity in the same animation frame")
        used.add(key)
        output.append({
            "animation": state, "frame_index": index,
            "event_id": event_id, "category": category,
            "frame_id": states[state]["frame_ids"][index],
        })
    output.sort(key=lambda item: (
        item["animation"], item["frame_index"], item["event_id"],
    ))
    grouped: dict[str, list[list[str]]] = {}
    for cue in output:
        key = f'{cue["animation"]}:{cue["frame_index"]}'
        grouped.setdefault(key, []).append([cue["category"], cue["event_id"]])
        if len(grouped[key]) > 16:
            raise SpriteCueError("one animation frame cannot emit more than 16 cues")
    result = {
        "schema_version": SCHEMA,
        "cues": output,
        "by_animation_frame": {
            key: grouped[key] for key in sorted(grouped)
        },
        "cue_count": len(output),
        "runtime_signal_only": True,
        "audio_and_vfx_effects_executed": False,
    }
    result["receipt_sha256"] = digest(result)
    return result


def verify_frame_cues(
    source: Mapping[str, Any], metadata: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Independently reproduce every cue from the authoritative source."""
    if not isinstance(metadata, Mapping):
        raise SpriteCueError("full verified original sprite metadata is required")
    actual = compile_frame_cues(source, metadata["animations"])
    if actual != metadata.get("frame_cues"):
        raise SpriteCueError("emitted sprite cue lineage differs from original source")
    return actual


def emit_godot_frame_cue_files(
    metadata: Mapping[str, Any], *, directory: str = "game/frontier/sprites",
) -> dict[str, str]:
    """Generate an actual Godot AnimatedSprite3D signal source and JSON."""
    if directory not in ("game/frontier/sprites", "sprites"):
        raise SpriteCueError("frame cue resource cannot escape known asset directories")
    asset = _id(metadata.get("asset_id"), "sprite asset")
    evidence = metadata.get("frame_cues")
    if evidence is None:
        return {}
    if not isinstance(evidence, dict):
        raise SpriteCueError("frame cue evidence must be a typed receipt")
    prior = dict(evidence)
    signed = prior.pop("receipt_sha256", None)
    if (signed != digest(prior) or evidence.get("schema_version") != SCHEMA
            or evidence.get("cue_count") != len(evidence.get("cues", []))
            or evidence.get("runtime_signal_only") is not True):
        raise SpriteCueError("frame cue receipt was changed or invented")
    compiled = compile_frame_cues(
        {"cues": [
            {key: entry[key] for key in (
                "animation", "frame_index", "event_id", "category",
            )}
            for entry in evidence["cues"]
        ]}, metadata["animations"],
    )
    if compiled != evidence:
        raise SpriteCueError("frame cue entries do not match original animation frames")
    table = json.dumps(
        evidence["by_animation_frame"], ensure_ascii=True,
        sort_keys=True, separators=(",", ":"),
    )
    code = "\n".join([
        "extends AnimatedSprite3D",
        "# Declarative cues from reviewed game source; NEVER script execution.",
        "signal cue_fired(event_id: String, category: String, animation_name: String, frame_index: int)",
        "const FRAME_CUES = " + table,
        "",
        "func _ready() -> void:",
        "    frame_changed.connect(_publish_frame_cues)",
        "    animation_changed.connect(_publish_frame_cues)",
        '    call_deferred("_publish_frame_cues")',
        "",
        "func _publish_frame_cues() -> void:",
        "    var name := str(animation)",
        '    var key := name + ":" + str(frame)',
        "    for item in FRAME_CUES.get(key, []):",
        "        cue_fired.emit(str(item[1]), str(item[0]), name, frame)",
        "",
    ])
    return {
        f"{directory}/{asset}.cues.json": json.dumps(
            evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ),
        f"{directory}/{asset}.cues.gd": code,
    }


def verify_godot_frame_cue_files(
    metadata: Mapping[str, Any], files: Mapping[str, str],
    *, directory: str = "game/frontier/sprites",
) -> dict[str, Any]:
    expected = emit_godot_frame_cue_files(metadata, directory=directory)
    if dict(files) != expected:
        raise SpriteCueError("published Godot frame-cue signal source differs")
    result = {
        "schema_version": "skeleton.jeeves.sprite_cue_resources.v1",
        "asset_id": metadata["asset_id"],
        "original_cue_receipt_sha256": (
            metadata["frame_cues"]["receipt_sha256"]
            if metadata.get("frame_cues") else None
        ),
        "verified_resource_hashes": {
            name: sha256(body.encode("utf-8")).hexdigest()
            for name, body in sorted(files.items())
        },
        "signal_source_reproduced": True,
        "audio_or_vfx_execution_verified": False,
    }
    result["receipt_sha256"] = digest(result)
    return result


__all__ = [
    "SpriteCueError", "compile_frame_cues", "verify_frame_cues",
    "emit_godot_frame_cue_files", "verify_godot_frame_cue_files",
]
