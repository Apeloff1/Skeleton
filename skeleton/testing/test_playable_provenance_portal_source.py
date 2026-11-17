"""Exact source reconstruction for the current Godot portal and eight modes.

Source-only acceptance. These tests never claim physical Godot execution,
device controls, model quality, original-content rights or release readiness.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from skeleton.forge.archetype_content import (
    archetype_files, attach_archetype_content, content_archetypes,
)
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.playable_portal import (
    SCRIPT_PATH, attach_playable_portal,
)
from skeleton.forge.playable_provenance import (
    SCHEMA, build_playable_receipt, verify_playable_source,
)
from skeleton.forge.playable_tuning import SOURCE_PATH
from skeleton.forge.source_manifest import source_manifest


def _build(mode: str, start: bool, axes: dict[str, float]):
    base = emit_godot(compile_era("extraction_now"))
    source = attach_archetype_content(base, mode, operator_axes=axes)
    files, _portal = attach_playable_portal(
        source, mode, start_in_prototype=start,
    )
    receipt = build_playable_receipt(
        files, mode, operator_axes=axes, start_in_prototype=start,
    )
    return base, files, receipt


@pytest.mark.parametrize("mode", content_archetypes())
@pytest.mark.parametrize("startup", (False, True))
def test_every_mode_and_startup_has_reconstructable_source(mode, startup):
    axes = {"tempo": 0.8, "risk": 0.9, "scarcity": 0.7}
    original, files, receipt = _build(mode, startup, axes)
    assert receipt["schema"] == SCHEMA
    assert receipt["mode"] == mode
    assert receipt["operator_axes"] == axes
    assert receipt["scene"] == f"res://scenes/archetypes/{mode}/main.tscn"
    assert receipt["launch_scene"] == (receipt["scene"] if startup else None)
    assert receipt["launcher"] == SCRIPT_PATH
    assert verify_playable_source(files, receipt)
    assert source_manifest(files)["file_count"] == len(files)
    assert files["data/rooms.json"] == original["data/rooms.json"]
    expected = archetype_files(mode, operator_axes=axes)
    assert all(files[key] == value for key, value in expected.items())
    assert receipt["source_files"] == {
        key: source_manifest(files)["files"][key]
        for key in sorted((*expected, SCRIPT_PATH))
    }
    assert SOURCE_PATH in files
    assert receipt["tuning"] == json.loads(files[SOURCE_PATH])
    # This is source proof, never physical or release certification.
    assert "device_certified" not in receipt
    assert "release_certified" not in receipt


def test_rehashing_adulterated_loop_cannot_forge_authored_source():
    _, files, receipt = _build(
        "racing", True, {"tempo": 0.6, "risk": 0.8},
    )
    path = "scripts/archetypes/racing/core_loop.gd"
    altered = dict(files)
    altered[path] += "\n# adulterated gameplay source\n"
    fake = deepcopy(receipt)
    manifest = source_manifest(altered)["files"]
    fake["source_files"] = {
        key: manifest[key] for key in fake["source_files"]
    }
    fake["source_sha256"] = hashlib.sha256(json.dumps(
        fake["source_files"], sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    assert not verify_playable_source(altered, fake)
    assert verify_playable_source(files, receipt)


@pytest.mark.parametrize("mutation", (
    lambda r: r.__setitem__("mode", "unreviewed"),
    lambda r: r.__setitem__("launcher", None),
    lambda r: r.__setitem__("scene", "res://untrusted.tscn"),
    lambda r: r.__setitem__("launch_scene", "res://untrusted.tscn"),
    lambda r: r.__setitem__("source_sha256", "0" * 64),
    lambda r: r["operator_axes"].__setitem__("tempo", 0.1),
    lambda r: r["tuning"]["axes"].__setitem__("tempo", 0.1),
    lambda r: r["source_files"].pop(SCRIPT_PATH),
))
def test_forged_identity_and_partial_inventory_are_rejected(mutation):
    _, files, receipt = _build(
        "survival", False, {"tempo": 0.9, "scarcity": 0.7},
    )
    fake = deepcopy(receipt)
    mutation(fake)
    assert not verify_playable_source(files, fake)
    assert verify_playable_source(files, receipt)


def test_portal_bytes_and_unpublished_source_are_denied():
    base = emit_godot(compile_era("extraction_now"))
    loose = attach_archetype_content(base, "puzzle")
    with pytest.raises(ValueError, match="portal"):
        build_playable_receipt(loose, "puzzle")
    _, files, receipt = _build("puzzle", False, {"opacity": 0.8})
    altered = dict(files)
    altered[SCRIPT_PATH] += "\n# altered portal\n"
    assert not verify_playable_source(altered, receipt)
    assert not verify_playable_source(files, {"schema": SCHEMA})
