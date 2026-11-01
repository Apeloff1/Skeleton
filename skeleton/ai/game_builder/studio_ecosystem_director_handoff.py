"""Playable HTML5 handoff integrating original scene timing and asset work orders.

The native asset and NPC execution contracts remain unqualified. The bundle
contains the *actual* independently replay-verified offline 2D preview, its
canonical winning proof, and two source-bound editor work orders.
"""
from __future__ import annotations

from hashlib import sha256
import io
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping
import zipfile

from .studio_ecosystem_catalog import compile_preview
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
    compile_scene_schedule,
)
from .studio_ecosystem_scene_asset_bindings import compile_scene_asset_bindings
from .studio_ecosystem_director_editor import render_director_editor
from .studio_ecosystem_director_choice_rehearsal import render_choice_rehearsal

SCHEMA = "skeleton.game_builder.studio_director_handoff.v1"
FILENAME = "studio_director_handoff.zip"
MAX_BUNDLE_BYTES = 8 * 1024 * 1024
_FILES = ("index.html", "director_editor.html", "choice_rehearsal.html",
          "scene_schedule.json",
          "scene_asset_bindings.json", "director_manifest.json")


def compile_director_handoff(
    documents: Mapping[str, Any], actions: list[list[str]],
    schedule: object, assignments: object, *,
    authorized: bool, expected_source_digest: str,
    expected_visual_digest: str,
    expected_session_digest: str | None = None,
) -> tuple[dict[str, object], bytes]:
    """Compile and package an exact, replayable original HTML5 director handoff."""
    if authorized is not True:
        raise PermissionError("studio director compilation requires operator authorization")
    _lease(expected_source_digest, "director canon")
    _lease(expected_visual_digest, "director visual")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "director session")
    timing = compile_scene_schedule(
        documents, actions, schedule, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    assets = compile_scene_asset_bindings(
        documents, actions, assignments, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_visual_digest=expected_visual_digest,
        expected_session_digest=expected_session_digest)
    if (timing["source_digest"] != assets["source_digest"]
            or timing["quest_source_digest"] != assets["quest_source_digest"]
            or timing["session_digest"] != assets["session_digest"]
            or timing["project_id"] != assets["project_id"]
            or timing["scene_count"] != assets["scene_count"]):
        raise StudioQuestError("director handoff source or scene contract diverged")
    if [row["scene_id"] for row in timing["timeline"]] != [
            row["scene_id"] for row in assets["scenes"]]:
        raise StudioQuestError("director scene order differs across source owners")
    # This existing compiler generates a real original offline 2D game and
    # demonstrates a winning trace. It does not instantiate NPC/asset designs.
    compiled = compile_preview(timing["project_id"], authorized=True)
    playable = compiled.playable.html.encode("utf-8", "strict")
    receipt = compiled.receipt()
    if (receipt.get("project_id") != timing["project_id"]
            or receipt.get("validated_gameplay_proof") is not True
            or sha256(playable).hexdigest() != receipt.get("html_sha256")):
        raise StudioQuestError("director playable compiler proof mismatch")
    editor_html, editor_receipt = render_director_editor(timing, assets)
    choice_html, choice_receipt = render_choice_rehearsal(
        documents, actions, timing, authorized=True,
        expected_source_digest=expected_source_digest)
    files = {
        "index.html": playable,
        "director_editor.html": editor_html,
        "choice_rehearsal.html": choice_html,
        "scene_schedule.json": _canonical(timing) + b"\n",
        "scene_asset_bindings.json": _canonical(assets) + b"\n",
    }
    manifest: dict[str, object] = {
        "schema": SCHEMA, "project_id": timing["project_id"],
        "source_digest": expected_source_digest,
        "visual_digest": expected_visual_digest,
        "quest_source_digest": timing["quest_source_digest"],
        "session_digest": timing["session_digest"],
        "scene_count": timing["scene_count"],
        "scene_schedule_digest": timing["schedule_digest"],
        "asset_binding_digest": assets["asset_binding_digest"],
        "canonical_playable_receipt": receipt,
        "offline_editor_receipt": editor_receipt,
        "offline_choice_rehearsal_receipt": choice_receipt,
        "file_hashes": {name: sha256(data).hexdigest()
                        for name, data in sorted(files.items())},
        "canonical_html5_gameplay_replay_verified": True,
        "native_scene_timing_verified": False,
        "npc_dialogue_executed_verified": False,
        "native_asset_binding_verified": False,
        "asset_rights_verified": False,
        "release_certified": False,
    }
    manifest["manifest_digest"] = _digest(manifest)
    files["director_manifest.json"] = _canonical(manifest) + b"\n"
    if sum(map(len, files.values())) > MAX_BUNDLE_BYTES:
        raise StudioQuestError("director handoff source exceeds byte budget")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, allowZip64=False) as archive:
        for name in _FILES:
            item = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100600 << 16
            archive.writestr(item, files[name])
    bundle = output.getvalue()
    if len(bundle) > MAX_BUNDLE_BYTES:
        raise StudioQuestError("director handoff archive exceeds byte budget")
    manifest["bundle_sha256"] = sha256(bundle).hexdigest()
    manifest["bundle_bytes"] = len(bundle)
    return manifest, bundle


def publish_director_handoff(manifest: Mapping[str, Any], bundle: bytes,
                             directory: Path, *, authorized: bool,
                             documents: Mapping[str, Any], actions: list[list[str]],
                             schedule: object, assignments: object) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("director publication requires operator authorization")
    if (type(manifest) is not dict or manifest.get("schema") != SCHEMA
            or type(bundle) is not bytes or not bundle
            or len(bundle) > MAX_BUNDLE_BYTES
            or sha256(bundle).hexdigest() != manifest.get("bundle_sha256")
            or len(bundle) != manifest.get("bundle_bytes")):
        raise StudioQuestError("invalid director handoff publication")
    rebuilt_manifest, rebuilt_bundle = compile_director_handoff(
        documents, actions, schedule, assignments, authorized=True,
        expected_source_digest=manifest.get("source_digest"),
        expected_visual_digest=manifest.get("visual_digest"),
        expected_session_digest=manifest.get("session_digest"))
    if manifest != rebuilt_manifest or bundle != rebuilt_bundle:
        raise StudioQuestError("director publication lacks canonical playable proof")
    directory_fd = _open_directory(directory)
    temporary = ".studio-director-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
        created = True
        try:
            _write_all(handle, bundle)
            os.fsync(handle)
        finally:
            os.close(handle)
        os.link(temporary, FILENAME, src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=directory_fd)
        finally:
            os.close(directory_fd)
    return {
        "path": str(Path(directory) / FILENAME),
        "bundle_sha256": manifest["bundle_sha256"],
        "bytes": len(bundle), "file_write_performed": True,
        "release_certified": False,
    }


def verify_director_handoff(
    documents: Mapping[str, Any], actions: list[list[str]],
    schedule: object, assignments: object, directory: Path, *,
    authorized: bool, expected_source_digest: str, expected_visual_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    """Independently rebuild and byte-compare an existing private handoff."""
    if authorized is not True:
        raise PermissionError("director restore requires operator authorization")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BUNDLE_BYTES:
                raise StudioQuestError("invalid director handoff archive")
            raw = os.read(handle, MAX_BUNDLE_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_BUNDLE_BYTES:
        raise StudioQuestError("invalid bounded director archive")
    manifest, expected = compile_director_handoff(
        documents, actions, schedule, assignments, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_visual_digest=expected_visual_digest,
        expected_session_digest=expected_session_digest)
    if raw != expected:
        raise StudioQuestError("director archive does not match source-bound replay")
    return manifest
