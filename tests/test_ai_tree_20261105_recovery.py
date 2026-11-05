"""Prevent source-bound AI-tree mirror drift and unclassified build roots."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_game_builder_mirror_is_identical():
    source = ROOT / "skeleton/forge/game_builder.py"
    mirror = ROOT / "skeleton/ai/forge/game_builder.py"
    assert mirror.read_bytes() == source.read_bytes()


def test_original_audio_source_has_exact_runtime_mirrors():
    for member in (
        "original_synthesis.py",
        "fixtures/footstep.json",
        "fixtures/harbor_chime.json",
    ):
        source = ROOT / "skeleton/audio" / member
        mirror = ROOT / "skeleton/ai/runtime/extensions/audio" / member
        assert mirror.read_bytes() == source.read_bytes(), member


def test_mass_build_root_is_explicitly_retained_without_cutover_authority():
    data = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    entries = [entry for entry in data["retained_outside_ai_tree"]
               if entry["path"] == "skeleton/mass_build"]
    assert len(entries) == 1
    assert entries[0]["owner"] and "no AI-runtime cutover" in entries[0]["reason"]
    assert data["pre_move_readiness"]["retained_outside_ai_tree_count"] == len(data["retained_outside_ai_tree"])
    assert data["implementation_signoff"]["signed"] is False
    assert data["verification_signoff"]["signed"] is False
