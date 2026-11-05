"""Regression for canonical Forge/audio mirrors and governed legacy mass-build."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_forge_game_builder_mirror_keeps_canonical_cli_behavior():
    canonical = ROOT / "skeleton" / "forge" / "game_builder.py"
    governed = ROOT / "skeleton" / "ai" / "forge" / "game_builder.py"
    assert ast.dump(ast.parse(canonical.read_text(encoding="utf-8")), include_attributes=False) == (
        ast.dump(ast.parse(governed.read_text(encoding="utf-8")), include_attributes=False)
    )
    assert 'argv[0] == "npc-schedule"' in governed.read_text(encoding="utf-8")


def test_audio_extension_mirrors_original_source_without_new_authority():
    for suffix in ["original_synthesis.py", "fixtures/footstep.json", "fixtures/harbor_chime.json"]:
        canonical = ROOT / "skeleton" / "audio" / suffix
        governed = ROOT / "skeleton" / "ai" / "runtime" / "extensions" / "audio" / suffix
        assert canonical.read_bytes() == governed.read_bytes(), suffix


def test_mass_build_is_explicitly_retained_not_promoted():
    manifest = json.loads((ROOT / "machine" / "ai_file_tree.json").read_text(encoding="utf-8"))
    owned = [item for item in manifest["retained_outside_ai_tree"]
             if item.get("path") == "skeleton/mass_build"]
    assert len(owned) == 1
    assert "owner" in owned[0] and "reason" in owned[0]
    assert all(item.get("destination") != "skeleton/mass_build" for item in manifest["mappings"])


def test_manifest_retained_root_count_matches_governed_catalog():
    manifest = json.loads((ROOT / "machine" / "ai_file_tree.json").read_text(encoding="utf-8"))
    assert manifest["pre_move_readiness"]["retained_outside_ai_tree_count"] == len(
        manifest["retained_outside_ai_tree"]
    )
    assert manifest["implementation_signoff"]["signed"] is False
    assert manifest["verification_signoff"]["signed"] is False
