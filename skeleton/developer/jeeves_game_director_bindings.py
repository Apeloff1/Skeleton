"""Machine-readable engine binding contract for canonical Director actions.

Bind runtime UI/controller events to typed game actions, scene exits, cinematic
cues and quest affordances. These are data contracts, not installed game code.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.jeeves.director_engine_bindings.v1"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _packet(root: Path, source: str) -> dict[str, Any]:
    world, source_sha = _load_world(root, source)
    stage_consumers: dict[str, list[dict[str, str]]] = {}
    for quest in world.quests:
        for stage in quest.stages:
            for sid in stage.scene_ids:
                stage_consumers.setdefault(sid, []).append({
                    "quest": quest.key, "stage": stage.key,
                    "quest_requires": list(quest.requires_quests),
                })
    scenes = []
    all_actions = 0
    for scene in world.scenes:
        transitions = [
            {
                "input": "ui_or_controller_select",
                "action": {"kind": "travel", "key": destination, "scene": scene.key},
                "destination_scene": destination,
                "checked_by": "Director.available_director_actions",
            }
            for destination in scene.links
        ]
        for affordance in scene.affordances:
            transitions.append({
                "input": "ui_or_controller_interact",
                "action": {"kind": "use", "key": affordance.key, "scene": scene.key},
                "affordance_kind": affordance.kind,
                "target": affordance.target,
                "checked_by": "Director.available_director_actions",
            })
        transitions.append({
            "input": "ui_or_controller_wait",
            "action": {"kind": "wait", "key": "wait", "scene": scene.key},
            "checked_by": "Director.available_director_actions",
        })
        all_actions += len(transitions)
        scenes.append({
            "key": scene.key, "region": scene.region,
            "camera_contract": scene.camera,
            "weather_contract": scene.weather,
            "lighting_contract": scene.lighting,
            "music_cue": scene.music, "style": scene.style,
            "cast": list(scene.cast), "props": list(scene.props),
            "stage_dependencies": stage_consumers.get(scene.key, []),
            "transitions": transitions,
            "cutscene_timelines": [
                {"key": c.key, "trigger": c.trigger, "skippable": c.skippable,
                 "cues": [x.payload() for x in c.cues]}
                for c in scene.cutscenes
            ],
        })
    return {
        "schema": SCHEMA, "project": world.project_id,
        "source": source, "source_sha256": source_sha,
        "world_sha256": world.digest, "scene_count": len(scenes),
        "declared_action_bindings": all_actions,
        "scene_bindings": scenes,
        "runtime_rule": "Re-evaluate available Director actions against the current canonical state before executing every event",
        "scene_rendering_implemented": False,
        "runtime_ui_wired_to_director": False,
        "audio_and_cinematic_playback_verified": False,
        "hardware_input_verified": False,
    }


def preview(root: Path, *, source: str) -> dict[str, Any]:
    packet = _packet(root, source)
    return {
        "ok": True, "action": "director-bindings",
        "candidate_sha256": _hash(packet), "bindings": packet,
        "persisted": False, "runtime_implemented": False,
    }


def _path(root: Path, identity: str) -> Path:
    if not isinstance(identity, str) or not DIGEST.fullmatch(identity):
        raise ValueError("binding contract digest must be an exact SHA-256")
    from skeleton.developer.jeeves_game_director_factory import _safe_design
    return _safe_design(root) / ("director_bindings_" + identity + ".json")


def publish(root: Path, *, source: str, approved_digest: str | None) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_authoring import _create_only
    packet = _packet(root, source)
    digest = _hash(packet)
    if approved_digest != digest:
        raise ValueError("--approve must match the exact Director engine binding digest")
    path = _path(root, digest)
    from skeleton.developer.jeeves_game_quality import _read
    if _read(root, source, 16 * 1024 * 1024)[1] != packet["source_sha256"]:
        raise ValueError("Director source changed while binding engine events")
    raw = (json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("Director engine bindings exceed source capacity")
    _create_only(path, raw)
    return {"ok": True, "action": "director-bindings-publish",
            "path": str(path), "candidate_sha256": digest,
            "runtime_implemented": False, "native_gameplay_verified": False}


def check(root: Path, *, source: str, digest: str) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_quality import _read
    path = _path(root, digest)
    packet, _ = _read(root, "design/" + path.name, 16 * 1024 * 1024)
    if packet != _packet(root, source) or _hash(packet) != digest:
        raise ValueError("Director engine binding packet differs from live original world")
    return {"ok": True, "action": "director-bindings-check",
            "candidate_sha256": digest, "binding_source_verified": True,
            "native_runtime_wired": False}
