"""User-facing source-authorized game evolution genuinely emits console/PC programs."""
from __future__ import annotations

import json

import pytest

from skeleton.ai.game_builder.native_evolution_cli import build_native_evolution


def _options(tmp_path, source: str, destination: str):
    rights = tmp_path / "my-original-authorship.txt"
    rights.write_text("I own the newly designed original maze and all original artwork.", encoding="utf-8")
    return dict(
        basis=source, destination=destination, project_id="owned-evolution",
        title="The Constellation Journals", seed=1982, width=17, height=15,
        levels=3, collectibles=3, hazards=4, health=4,
        rights_evidence=rights,
        creative_identity=("original-to-me maze", "distinctive hand-made constellation motif"),
        output=tmp_path / "generated-games", reverse=False,
    )


def test_historical_vic20_to_c64_campaign_emits_actual_new_native_6510_source(tmp_path):
    args = _options(tmp_path, "commodore_vic20", "commodore_64")
    receipt = build_native_evolution(**args, authorized=True)
    assert receipt["campaign_stage_count"] == 1
    assert receipt["native_source_stages"] == 1
    assert receipt["design_only_stages"] == 0
    assert receipt["stage_dispositions"][0]["platform"] == "commodore_64"
    assert receipt["stage_dispositions"][0]["source_kind"] == "native_c64_cc65_prg_source"
    project = args["output"] / "stage-01-commodore_64"
    assert (project / "game.c").is_file()
    assert (project / "Makefile").is_file()
    manifest = json.loads((project / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["target_platform_id"] == "commodore_64"
    assert manifest["emulator_verified"] is False
    assert receipt["binary_built"] is False
    assert receipt["rights_independently_verified"] is False


def test_handheld_design_evolution_emits_game_boy_machine_source_and_keeps_unbuilt_stages_visible(tmp_path):
    args = _options(tmp_path, "nintendo_game_watch", "nintendo_game_boy_color")
    receipt = build_native_evolution(**args, authorized=True)
    assert receipt["campaign_stage_count"] == 2
    assert receipt["native_source_stages"] == 1
    assert receipt["design_only_stages"] == 1
    assert (args["output"] / "stage-01-nintendo_game_boy" / "main.asm").is_file()
    assert not (args["output"] / "stage-02-nintendo_game_boy_color").exists()
    assert receipt["stage_dispositions"][0]["source_kind"] == "game_boy_dmg_rgbds_source"
    assert receipt["stage_dispositions"][1]["status"] == "design_only"
    assert all(stage["hardware_verified"] is False for stage in receipt["stage_dispositions"])


def test_native_evolution_rejects_unauthorized_cross_project_unknown_or_reused_output(tmp_path):
    args = _options(tmp_path, "commodore_vic20", "commodore_64")
    with pytest.raises(PermissionError):
        build_native_evolution(**args, authorized=False)
    assert not args["output"].exists()
    with pytest.raises(ValueError, match="validated catalogue"):
        build_native_evolution(**(args | {"destination": "fake_console"}), authorized=True)
    with pytest.raises(ValueError, match="ordinary"):
        build_native_evolution(**(args | {"rights_evidence": tmp_path / "missing"}), authorized=True)
    assert not args["output"].exists()
    build_native_evolution(**args, authorized=True)
    with pytest.raises(FileExistsError):
        build_native_evolution(**args, authorized=True)
