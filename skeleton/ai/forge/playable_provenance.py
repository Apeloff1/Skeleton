"""Reconstruct and verify the bounded native playable game source.

This is deterministic source identity, not device, model, rights, anti-cheat,
installer or release certification. A self-consistent unkeyed digest of
adulterated GDScript never qualifies as original authored source.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from skeleton.forge.archetype_content import archetype_files, content_archetypes
from skeleton.forge.playable_portal import (
    SCRIPT_PATH, verify_playable_portal,
)
from skeleton.forge.playable_tuning import SOURCE_PATH
from skeleton.forge.source_manifest import source_manifest

SCHEMA = "skeleton.gameforge.playable_source.v1"
_REQUIRED = frozenset({
    "schema", "mode", "scene", "launch_scene", "launcher",
    "operator_axes", "source_files", "source_sha256",
})
_OPTIONAL = frozenset({"tuning"})


def _digest(source_files: Mapping[str, str]) -> str:
    return hashlib.sha256(json.dumps(
        source_files, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def verify_playable_source(
    files: Mapping[str, str], receipt: Mapping[str, Any],
) -> bool:
    """Verify exact authorized templates, portal, tuning and source inventory."""
    try:
        if type(files) is not dict or type(receipt) is not dict:
            return False
        if not _REQUIRED.issubset(receipt) or set(receipt) - _REQUIRED - _OPTIONAL:
            return False
        if receipt["schema"] != SCHEMA:
            return False
        mode = receipt["mode"]
        if type(mode) is not str or mode not in content_archetypes():
            return False
        scene = f"res://scenes/archetypes/{mode}/main.tscn"
        if receipt["scene"] != scene:
            return False
        startup = receipt["launch_scene"] is not None
        if receipt["launch_scene"] != (scene if startup else None):
            return False
        # The verified CanvasLayer portal exists for both startup modes.
        if receipt["launcher"] != SCRIPT_PATH:
            return False
        if not verify_playable_portal(files, mode, start_in_prototype=startup):
            return False
        axes = receipt["operator_axes"]
        if type(axes) is not dict:
            return False
        expected = archetype_files(mode, operator_axes=axes)
        native_tuning = (
            json.loads(expected[SOURCE_PATH])
            if SOURCE_PATH in expected else None
        )
        if receipt.get("tuning") != native_tuning:
            return False
        if ("tuning" in receipt) != (native_tuning is not None):
            return False
        if any(files.get(path) != body for path, body in expected.items()):
            return False
        # Portal verification has already reconstructed and checked its exact
        # mode-specific script; include its bytes in the source inventory.
        expected[SCRIPT_PATH] = files[SCRIPT_PATH]
        manifest = source_manifest(files)
        source_files = {
            path: manifest["files"][path] for path in sorted(expected)
        }
        return (
            type(receipt["source_files"]) is dict
            and receipt["source_files"] == source_files
            and receipt["source_sha256"] == _digest(source_files)
        )
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return False


def build_playable_receipt(
    files: dict[str, str], mode: str, *,
    operator_axes: Mapping[str, float] | None = None,
    start_in_prototype: bool = False,
) -> dict[str, Any]:
    """Build a reproducible provenance receipt only for verified source.

    The caller must not publish this as physical Godot/device qualification.
    """
    if type(start_in_prototype) is not bool:
        raise ValueError("playable startup must be an explicit boolean")
    if type(mode) is not str or mode not in content_archetypes():
        raise ValueError("unsupported native playable source identity")
    axes = dict(operator_axes or {})
    expected = archetype_files(mode, operator_axes=axes)
    if not verify_playable_portal(files, mode, start_in_prototype=start_in_prototype):
        raise ValueError("playable portal source identity failed")
    if any(files.get(path) != body for path, body in expected.items()):
        raise ValueError("playable authored source identity failed")
    expected[SCRIPT_PATH] = files[SCRIPT_PATH]
    manifest = source_manifest(files)
    source_files = {path: manifest["files"][path] for path in sorted(expected)}
    scene = f"res://scenes/archetypes/{mode}/main.tscn"
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "mode": mode,
        "scene": scene,
        "launch_scene": scene if start_in_prototype else None,
        "launcher": SCRIPT_PATH,
        "operator_axes": axes,
        "source_files": source_files,
        "source_sha256": _digest(source_files),
    }
    if SOURCE_PATH in expected:
        receipt["tuning"] = json.loads(expected[SOURCE_PATH])
    if not verify_playable_source(files, receipt):
        raise ValueError("playable source provenance reconstruction failed")
    return receipt


__all__ = ["SCHEMA", "build_playable_receipt", "verify_playable_source"]
