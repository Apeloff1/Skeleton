"""Real source-package porting between SMS and Game Gear from one original world.

No commercial files, firmware, console ROMs or binary-build claims are
created by this test. The GCC test executes each emitted gameplay C against
its own independently generated original winning route.
"""
from __future__ import annotations

from hashlib import sha256
import json
import shutil

import pytest

from scripts.game_builder.sega8_dual_homebrew_cli import (
    Sega8DualPortError, export_dual_original,
)
from scripts.game_builder.sega8_source_replay import run_host_replay


def _author(tmp_path):
    path=tmp_path/"authorship.txt"
    path.write_text(
        "The worlds, tiles, palette, companion and all game art are mine.",
        encoding="utf-8",
    )
    return path


def _config(tmp_path, theme="ocean", stages=2):
    path=tmp_path/"original-game.json"
    path.write_text(json.dumps({
        "project_id":"author-original-game-portability",
        "title":"Original Lighthouse Odyssey",
        "seed":76543,
        "theme":theme,
        "levels":stages,
        "width":15,
        "height":13,
        "collectibles_per_level":3,
        "hazards_per_level":2,
        "starting_health":4,
    },sort_keys=True),encoding="utf-8")
    return path


@pytest.mark.parametrize("theme",("forest","space","desert","ocean","arcade"))
def test_actual_original_game_dual_console_source_custody(theme,tmp_path):
    author=_author(tmp_path)
    config=_config(tmp_path,theme=theme,stages=1)
    output=tmp_path/"native-original"
    proof=export_dual_original(
        output,author,profile="custom_original",game_config_path=config,
    )
    assert proof["schema"]=="skeleton.game_builder.original_sega8_dual_port_source.v1"
    assert proof["project_id"]=="author-original-game-portability"
    assert proof["portability_identity_verified"] is True
    assert proof["actual_native_rom_built"] is False
    assert proof["full_hardware_emulator_verified"] is False
    assert proof["physical_hardware_verified"] is False
    assert proof["release_approved"] is False
    assert proof["distribution_licensed"] is False
    assert proof["original_rights_independently_verified"] is False
    assert proof["third_party_rom_or_firmware_included"] is False
    assert len(proof["receipt_sha256"])==64
    assert json.loads((output/"portability.json").read_text())==proof
    targets=proof["independently_generated_native_sources"]
    assert set(targets)=={"sega_master_system","sega_game_gear"}
    assert targets["sega_master_system"]["source_sha256"] != targets["sega_game_gear"]["source_sha256"]
    assert len({targets[t]["original_reference_sha256"] for t in targets})==2
    for target in targets:
        path=output/target
        source=sha256(b"\0".join(
            (path/leaf).read_bytes()
            for leaf in ("game.c","Makefile","manifest.json")
        )).hexdigest()
        manifest=json.loads((path/"manifest.json").read_text())
        assert source==targets[target]["source_sha256"]
        assert manifest["world_digest"]==proof["world_digest"]
        assert manifest["original_demo_solution_sha256"]==proof["original_solution_sha256"]
        assert manifest["source_rights_evidence_sha256"]==proof["author_declaration_sha256"]
        assert manifest["original_color_theme"]==theme
        assert manifest["native_per_stage_hardware_bg_palette_accents"] is True
        assert manifest["binary_compiled"] is False
        assert manifest["release_approved"] is False
        assert not (path/"build").exists()


@pytest.mark.skipif(not shutil.which("gcc"),reason="host C compiler required")
def test_both_distinct_native_game_c_outputs_replay_same_original_game(tmp_path):
    author=_author(tmp_path)
    output=tmp_path/"ported-homebrew"
    proof=export_dual_original(
        output,author,profile="custom_original",
        game_config_path=_config(tmp_path,"arcade",stages=2),
    )
    host_traces={}
    for target in ("sega_master_system","sega_game_gear"):
        result=run_host_replay(
            output/target,output/(target+"-original-reference.json"),
        )
        assert result["original_levels_verified"]==2
        assert result["all_level_completion_verified"] is True
        assert result["original_demo_controller_actions_verified"]==result["original_controller_actions_verified"]
        assert result["original_native_solution_attract_mode_host_verified"] is True
        assert result["world_digest"]==proof["world_digest"]
        assert result["source_content_digest"]==proof["independently_generated_native_sources"][target]["source_sha256"]
        host_traces[target]=result["original_demo_screen_trace_sha256"]
    assert host_traces["sega_master_system"]==host_traces["sega_game_gear"]


@pytest.mark.parametrize("profile,config",(
    ("custom_original",None),
    ("standard",{"title":"not permitted"}),
    ("full_campaign",{"seed":1}),
    ("counterfeit",None),
))
def test_failed_dual_game_custody_never_creates_approved_output(tmp_path,profile,config):
    author=_author(tmp_path)
    data=None
    if config is not None:
        data=tmp_path/"forged-config.json"
        data.write_text(json.dumps(config),encoding="utf-8")
    root=tmp_path/"must-not-exist"
    with pytest.raises((ValueError,TypeError)):
        export_dual_original(root,author,profile=profile,game_config_path=data)
    assert not root.exists()


@pytest.mark.parametrize("mutated",(
    {"project_id":"owned","title":"New Original","seed":1,
     "theme":"space","levels":1,"width":21},
    {"project_id":"owned","title":"New Original","seed":1,
     "theme":"space","levels":1,"height":17},
    {"project_id":"owned","title":"New Original","seed":1,
     "theme":["commercial"],"levels":1},
    {"project_id":"owned","title":"New Original","seed":True,
     "theme":"space","levels":1},
    {"project_id":"owned","title":"New Original","seed":1,
     "theme":"space","levels":1,"licensed_rom":"outside.sms"},
))
def test_dual_game_porter_never_exports_unsafe_original_configuration(tmp_path,mutated):
    author=_author(tmp_path)
    config=tmp_path/"candidate.json"
    config.write_text(json.dumps(mutated),encoding="utf-8")
    root=tmp_path/"not-approved"
    with pytest.raises((Sega8DualPortError,ValueError)):
        export_dual_original(root,author,profile="custom_original",
                             game_config_path=config)
    assert not root.exists()


def test_original_project_is_never_overwritten_by_porting(tmp_path):
    author=_author(tmp_path)
    output=tmp_path/"protected-project"
    output.mkdir()
    original=output/"my-original-game.txt"
    original.write_text("Do not overwrite or replace",encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_dual_original(output,author)
    assert original.read_text()=="Do not overwrite or replace"
    assert not (output/"portability.json").exists()


def test_symlinked_untrusted_original_config_fails_closed(tmp_path):
    author=_author(tmp_path)
    config=_config(tmp_path)
    link=tmp_path/"unreviewed.json"
    link.symlink_to(config)
    with pytest.raises(Sega8DualPortError,match="ordinary JSON"):
        export_dual_original(
            tmp_path/"not-approved",author,profile="custom_original",
            game_config_path=link,
        )
    assert not (tmp_path/"not-approved").exists()
