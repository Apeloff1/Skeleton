"""Deterministic authored caption and audio cue rehearsal for studio scenes.

No samples are synthesized or played. Every cue binds an authored source layer
to an exact canonical quest replay and scene schedule; output is an accessible
caption plan for a playable director, not evidence of recorded or licensed audio.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory,
    compile_scene_schedule,
)

SCHEMA = "skeleton.game_builder.studio_audio_cue_plan.v1"
REQUEST_SCHEMA = "skeleton.game_builder.studio_audio_cue_authoring.v1"
FILENAME = "studio_audio_cues.json"
MAX_CUES = 256
MAX_SCENES = 64
MAX_BYTES = 256 * 1024
MAX_CAPTION = 280


def _text(value: object, label: str, *, maximum: int = MAX_CAPTION) -> str:
    if (type(value) is not str or not value or len(value) > maximum
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise StudioQuestError("invalid audio " + label)
    return value


def _number(value: object, label: str, *, minimum: int = 0,
            maximum: int = 1_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise StudioQuestError("invalid audio " + label)
    return value


def _layers(documents: Mapping[str, Any]) -> tuple[str, dict[str, dict[str, str]]]:
    audio = documents.get("audio")
    if type(audio) is not dict or audio.get("release_certified") is not False:
        raise StudioQuestError("missing canonical non-certified audio source")
    layers = audio.get("sound_layers")
    if type(layers) is not list or not 1 <= len(layers) <= 64:
        raise StudioQuestError("authored sound layer list required")
    accessibility = audio.get("audio_accessibility")
    if (type(accessibility) is not list
            or any(type(value) is not str for value in accessibility)
            or not {"complete_captions", "no_audio_only_navigation"}.issubset(
                set(accessibility))):
        raise StudioQuestError("authored caption and non-audio navigation obligations missing")
    mapped: dict[str, dict[str, str]] = {}
    for layer in layers:
        if type(layer) is not dict or not {"id", "source", "trigger", "ducking", "spatial"}.issubset(layer):
            raise StudioQuestError("invalid authored sound layer")
        key = _text(layer["id"], "layer ID", maximum=80)
        if key in mapped:
            raise StudioQuestError("duplicate sound layer ID")
        mapped[key] = {
            "source": _text(layer["source"], "source description", maximum=512),
            "trigger": _text(layer["trigger"], "trigger", maximum=256),
            "ducking": _text(layer["ducking"], "ducking", maximum=80),
            "spatial": _text(layer["spatial"], "spatial", maximum=80),
        }
    return _digest(audio), mapped


def _validate_request(request: object, scene_ids: set[str]) -> dict[str, Any]:
    if (type(request) is not dict or set(request) != {"schema", "scene_cues"}
            or request.get("schema") != REQUEST_SCHEMA):
        raise StudioQuestError("invalid typed audio cue authoring request")
    cues = request["scene_cues"]
    if type(cues) is not dict or set(cues) != scene_ids:
        raise StudioQuestError("audio cue scene identities differ from canonical schedule")
    if len(_canonical(request)) > 64 * 1024:
        raise StudioQuestError("audio cue authoring request exceeds budget")
    return request


def compile_audio_cues(
    documents: Mapping[str, Any], actions: list[list[str]], schedule: object,
    request: object, *, authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, Any]:
    """Compile a bounded timeline with source, schedule, and session custody."""
    if authorized is not True:
        raise PermissionError("audio cue compilation requires operator authorization")
    _lease(expected_source_digest, "audio source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "audio session")
    timing = compile_scene_schedule(
        documents, actions, schedule, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    audio_digest, layers = _layers(documents)
    rows = timing["timeline"]
    if not 1 <= len(rows) <= MAX_SCENES:
        raise StudioQuestError("invalid audio scene count")
    authored = _validate_request(request, {row["scene_id"] for row in rows})
    result_rows: list[dict[str, Any]] = []
    total = 0
    for scene in rows:
        scene_id = scene["scene_id"]
        authored_cues = authored["scene_cues"][scene_id]
        if type(authored_cues) is not list or not 1 <= len(authored_cues) <= 16:
            raise StudioQuestError("each scene requires 1-16 authored caption cues")
        used: dict[str, int] = {}
        cues: list[dict[str, Any]] = []
        for cue in authored_cues:
            if type(cue) is not dict or set(cue) != {
                    "layer_id", "start_offset", "duration_ticks", "caption"}:
                raise StudioQuestError("invalid audio cue fields")
            layer_id = _text(cue["layer_id"], "cue layer", maximum=80)
            if layer_id not in layers:
                raise StudioQuestError("audio cue references unregistered sound layer")
            offset = _number(cue["start_offset"], "cue offset")
            duration = _number(cue["duration_ticks"], "cue duration", minimum=1)
            if offset + duration > scene["duration_ticks"]:
                raise StudioQuestError("audio cue exceeds authored scene duration")
            if offset < used.get(layer_id, 0):
                raise StudioQuestError("same-layer audio cues overlap or are out of order")
            used[layer_id] = offset + duration
            caption = _text(cue["caption"], "caption")
            absolute_start = scene["start_tick"] + offset
            entry: dict[str, Any] = {
                "scene_id": scene_id, "layer_id": layer_id,
                "start_tick": absolute_start,
                "end_tick": absolute_start + duration,
                "caption": caption,
                "trigger": layers[layer_id]["trigger"],
                "ducking": layers[layer_id]["ducking"],
                "spatial": layers[layer_id]["spatial"],
                "authored_source": layers[layer_id]["source"],
                "audio_recording_verified": False,
                "caption_runtime_verified": False,
            }
            entry["cue_digest"] = _digest(entry)
            cues.append(entry)
            total += 1
            if total > MAX_CUES:
                raise StudioQuestError("audio cue budget exceeded")
        scene_row: dict[str, Any] = {
            "scene_id": scene_id, "scene_proof_digest": scene["scene_proof_digest"],
            "start_tick": scene["start_tick"], "end_tick": scene["end_tick"],
            "cues": cues,
        }
        scene_row["scene_audio_digest"] = _digest(scene_row)
        result_rows.append(scene_row)
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": timing["project_id"],
        "source_digest": timing["source_digest"],
        "quest_source_digest": timing["quest_source_digest"],
        "session_digest": timing["session_digest"],
        "schedule_digest": timing["schedule_digest"],
        "audio_source_digest": audio_digest,
        "request_digest": _digest(authored),
        "scene_count": len(result_rows), "cue_count": total,
        "scenes": result_rows, "source_replay_verified": True,
        "captions_authored": True, "captions_rendered_verified": False,
        "audio_recorded_verified": False, "native_audio_verified": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES:
        raise StudioQuestError("audio cue receipt exceeds bounded size")
    result["plan_digest"] = _digest(result)
    return result


def _verify_plan(
    plan: Mapping[str, Any], documents: Mapping[str, Any],
    actions: list[list[str]], schedule: object, request: object,
) -> bytes:
    if type(plan) is not dict or plan.get("schema") != SCHEMA:
        raise StudioQuestError("invalid audio plan receipt")
    expected = compile_audio_cues(
        documents, actions, schedule, request, authorized=True,
        expected_source_digest=_lease(plan.get("source_digest"), "published audio source"),
        expected_session_digest=_lease(plan.get("session_digest"), "published audio session"))
    if _canonical(expected) != _canonical(plan):
        raise StudioQuestError("audio plan is not canonical source replay")
    return _canonical(plan) + b"\n"


def publish_audio_cues(
    plan: Mapping[str, Any], directory: Path, *, authorized: bool,
    documents: Mapping[str, Any], actions: list[list[str]],
    schedule: object, request: object,
) -> dict[str, Any]:
    """Create a private, exclusive receipt without following directory symlinks."""
    if authorized is not True:
        raise PermissionError("audio cue publication requires operator authorization")
    data = _verify_plan(plan, documents, actions, schedule, request)
    import secrets
    directory_fd = _open_directory(directory)
    fd: int | None = None
    temporary = ".studio_audio_" + secrets.token_hex(16) + ".tmp"
    temporary_created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        temporary_created = True
        offset = 0
        while offset < len(data):
            count = os.write(fd, data[offset:])
            if count <= 0:
                raise OSError("short audio cue write")
            offset += count
        os.fsync(fd)
        os.close(fd)
        fd = None
        # Publish only fully durable bytes; never overwrite an existing receipt.
        os.link(temporary, FILENAME, src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        if temporary_created:
            os.unlink(temporary, dir_fd=directory_fd)
        os.close(directory_fd)
    return {
        "schema": SCHEMA, "plan_digest": plan["plan_digest"],
        "filename": FILENAME, "bytes": len(data),
        "sha256": sha256(data).hexdigest(), "file_write_performed": True,
        "release_certified": False,
    }


def verify_published_audio_cues(
    directory: Path, *, documents: Mapping[str, Any],
    actions: list[list[str]], schedule: object, request: object,
    expected_source_digest: str, expected_session_digest: str | None = None,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("audio cue verification requires operator authorization")
    expected = compile_audio_cues(
        documents, actions, schedule, request, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    directory_fd = _open_directory(directory)
    try:
        fd = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            if os.fstat(fd).st_size > MAX_BYTES + 1:
                raise StudioQuestError("published audio plan exceeds byte budget")
            chunks: list[bytes] = []
            remaining = MAX_BYTES + 2
            while remaining:
                part = os.read(fd, min(remaining, 65536))
                if not part:
                    break
                chunks.append(part)
                remaining -= len(part)
            data = b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)
    if data != _canonical(expected) + b"\n":
        raise StudioQuestError("published audio cue plan failed exact replay")
    return expected


__all__ = [
    "SCHEMA", "REQUEST_SCHEMA", "FILENAME", "compile_audio_cues",
    "publish_audio_cues", "verify_published_audio_cues",
]
