"""Deterministic source reconstruction for the native playable prototype.

A self-consistent SHA-256 manifest alone is not a claim of *authored*
gameplay: an arbitrary changed GDScript could be hashed again. This module
reconstructs exact, known original-game source from the fixed registry and
bounded cockpit edits, checks the selected startup/launcher path, and
compares every path and receipt to that source.

This is source convergence and integrity, not authentication or anti-cheat;
an attacker able to modify this verifier is outside its scope.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from skeleton.forge.archetype_content import (
    PLAYABLE_LAUNCHER_PATH, _LAUNCHER_SCRIPT,
    archetype_files, content_archetypes,
)
from skeleton.forge.playable_tuning import SOURCE_PATH
from skeleton.forge.source_manifest import source_manifest

SCHEMA = "skeleton.gameforge.playable_source.v1"


def verify_playable_source(
    files: Mapping[str, str], receipt: Mapping[str, Any],
) -> bool:
    """Require emitted game source to equal a reproducible authored build."""
    try:
        if type(receipt) is not dict or type(files) is not dict:
            return False
        required = {
            "schema", "mode", "scene", "launch_scene", "launcher",
            "source_files", "source_sha256",
        }
        optional = {"tuning"}
        if not required.issubset(receipt) or set(receipt) - required - optional:
            return False
        if receipt.get("schema") != SCHEMA:
            return False
        mode = receipt["mode"]
        if type(mode) is not str or mode not in content_archetypes():
            return False
        project = files.get("project.godot")
        if type(project) is not str:
            return False
        scene = f"res://scenes/archetypes/{mode}/main.tscn"
        if receipt.get("scene") != scene:
            return False
        start = receipt["launch_scene"]
        launcher = receipt["launcher"]
        if (start is None) == (launcher is None):
            return False
        if start is not None:
            if start != scene or project.count(f'run/main_scene="{scene}"') != 1:
                return False
            if PLAYABLE_LAUNCHER_PATH in files or "PlayableHub=" in project:
                return False
        else:
            if launcher != PLAYABLE_LAUNCHER_PATH:
                return False
            if project.count('run/main_scene="res://scenes/levels/run_level.tscn"') != 1:
                return False
            if project.count(
                'PlayableHub="*res://scripts/autoloads/playable_hub.gd"'
            ) != 1:
                return False

        tuning = receipt.get("tuning")
        if tuning is not None:
            if type(tuning) is not dict or type(tuning.get("axes")) is not dict:
                return False
            edits = tuning["axes"]
        else:
            edits = None
        expected = archetype_files(mode, tuning=edits)
        if tuning is None and SOURCE_PATH in files:
            return False
        if tuning is not None:
            if SOURCE_PATH not in expected or json.loads(expected[SOURCE_PATH]) != tuning:
                return False
        if launcher is not None:
            expected[PLAYABLE_LAUNCHER_PATH] = _LAUNCHER_SCRIPT.replace(
                "__MODE__", mode,
            )
        if any(files.get(path) != content for path, content in expected.items()):
            return False

        manifest = source_manifest(files)
        source_files = {path: manifest["files"][path] for path in sorted(expected)}
        if receipt.get("source_files") != source_files:
            return False
        digest = hashlib.sha256(json.dumps(
            source_files, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        return receipt.get("source_sha256") == digest
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return False


__all__ = ["SCHEMA", "verify_playable_source"]
