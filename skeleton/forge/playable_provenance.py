"""Exact source reconstruction for the active native prototype and portal.

The v2 contract binds the actual bidirectional portal, project settings and
generated native code, not the retired PlayableHub or an arbitrary digest.
Source convergence is not native execution evidence or release authority.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from skeleton.forge.archetype_content import archetype_files, content_archetypes, verify_archetype_content
from skeleton.forge.playable_portal import SCRIPT_PATH, verify_playable_portal
from skeleton.forge.playable_tuning import SOURCE_PATH
from skeleton.forge.source_manifest import source_manifest

SCHEMA = "skeleton.gameforge.playable_source.v2"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def build_playable_source_receipt(
    files: dict[str, str], mode: str, *,
    operator_axes: Mapping[str, float] | None = None,
    start_in_prototype: bool = False,
) -> dict[str, Any]:
    """Reconstruct all governed native files after independent feature writers."""
    if type(files) is not dict or type(mode) is not str or mode not in content_archetypes():
        raise ValueError("invalid playable source inventory")
    if type(start_in_prototype) is not bool:
        raise ValueError("explicit playable startup selection required")
    manifest = source_manifest(files)
    if not verify_archetype_content(files, mode, operator_axes=operator_axes):
        raise ValueError("native playable source differs from authored generator")
    if not verify_playable_portal(files, mode, start_in_prototype=start_in_prototype):
        raise ValueError("native playable portal or startup source invalid")
    expected = archetype_files(mode, operator_axes=operator_axes)
    owned = {path for path in files if path.casefold().startswith(
        ("scenes/archetypes/", "scripts/archetypes/"))}
    authored = {path for path in expected if path != SOURCE_PATH}
    if owned != authored:
        raise ValueError("unreviewed native prototype source in governed namespace")
    paths = sorted(set(expected) | {SCRIPT_PATH, "project.godot"})
    hashes = {path: manifest["files"][path] for path in paths}
    scene = f"res://scenes/archetypes/{mode}/main.tscn"
    receipt = {
        "schema": SCHEMA, "mode": mode, "scene": scene,
        "launch_scene": scene if start_in_prototype else None,
        "launcher": SCRIPT_PATH, "source_files": hashes,
        "source_sha256": hashlib.sha256(_canonical(hashes)).hexdigest(),
        "native_execution_qualified": False,
    }
    if SOURCE_PATH in expected:
        receipt["tuning"] = json.loads(expected[SOURCE_PATH])
    return receipt


def verify_playable_source(files: Mapping[str, str], receipt: Mapping[str, Any]) -> bool:
    """Reconstruct the current contract; never promote a historical v1 receipt."""
    try:
        if type(files) is not dict or type(receipt) is not dict or receipt.get("schema") != SCHEMA:
            return False
        mode = receipt["mode"]
        launch = receipt["launch_scene"]
        scene = f"res://scenes/archetypes/{mode}/main.tscn"
        if launch is not None and launch != scene:
            return False
        tuning = receipt.get("tuning")
        if tuning is not None and (type(tuning) is not dict or type(tuning.get("axes")) is not dict):
            return False
        expected = build_playable_source_receipt(
            files, mode, operator_axes=None if tuning is None else tuning["axes"],
            start_in_prototype=launch is not None,
        )
        return _canonical(receipt) == _canonical(expected)
    except (KeyError, TypeError, ValueError, RuntimeError, OverflowError, AttributeError, RecursionError):
        return False


__all__ = ["SCHEMA", "build_playable_source_receipt", "verify_playable_source"]
