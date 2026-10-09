"""Original game portfolio exports actual machine source trees, atomically and safely."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.ai.game_builder.native_game_cli import _NATIVE
from skeleton.ai.game_builder.native_portfolio_cli import (
    NativePortfolioError, compile_native_portfolio,
)


def _arguments(tmp_path):
    evidence=tmp_path/"author-wrote-this.txt"
    evidence.write_text("My entirely new original worlds, art and game mechanics.",encoding="utf-8")
    return {
        "basis":"bandai_wonderswan",
        "project_id":"original-cross-era-game",
        "title":"Star Crystal Adventure",
        "seed":190846,
        "rights_evidence":evidence,
        "creative_identity":("new constellation gameplay","original artwork and original levels"),
        "output":tmp_path/"all-original-platforms",
        "authorized":True,
        "width":17,"height":15,"levels":3,
        "collectibles":3,"hazards":4,"health":4,
    }


def test_full_portfolio_really_exports_all_supported_native_machine_sources(tmp_path):
    args=_arguments(tmp_path)
    report=compile_native_portfolio(**args)
    assert report["target_count"]==len(_NATIVE)==10
    assert report["original_project_id"]==args["project_id"]
    assert report["rights_to_distribute"] is False
    assert report["binary_compilation_executed"] is False
    assert report["any_emulator_playthrough_verified"] is False
    assert report["independent_legal_clearance_verified"] is False
    assert len(report["portfolio_digest"])==64
    root=args["output"]
    assert root.is_dir()
    assert json.loads((root/"portfolio-manifest.json").read_text(encoding="utf-8"))=={
        key:value for key,value in report.items() if key!="output_directory"
    }
    mapping={
        "apple_ii":"game.c",
        "atari_400_800":"game.c",
        "commodore_64":"game.c",
        "dos_vga":"game.asm",
        "nintendo_game_boy":"main.asm",
        "nintendo_game_boy_color":"main.asm",
        "nintendo_famicom":"main.s",
        "windows_modern":"game.c",
        "linux_desktop":"game.c",
        "macos_modern":"game.c",
    }
    assert set(mapping)==set(_NATIVE)
    assert {p.name for p in (root/"targets").iterdir()}==set(_NATIVE)
    for item in report["native_projects"]:
        game=root/item["relative_source_directory"]
        assert (game/mapping[item["platform"]]).is_file()
        assert (game/"manifest.json").is_file()
        assert item["world_digest"]==report["original_world_digest"]
        assert item["reference_replay_digest"]==report["original_safe_replay_digest"]
        assert item["native_binary_built"] is False
        assert len(item["native_source_digest"])==64
    # Hardware-specific code must not be a renamed copy of a web app.
    assert "CGBBackgroundPalette:" in (root/"targets/nintendo_game_boy_color/main.asm").read_text()
    assert "SPEAKER" in (root/"targets/apple_ii/game.c").read_text()
    assert "org 100h" in (root/"targets/dos_vga/game.asm").read_text()
    assert "0xD200" in (root/"targets/atari_400_800/game.c").read_text()
    with pytest.raises(FileExistsError):
        compile_native_portfolio(**args)


def test_portfolio_is_reproducible_across_independent_output_directories(tmp_path):
    args=_arguments(tmp_path)
    one=compile_native_portfolio(**(args|{"targets":("nintendo_game_boy_color","apple_ii")}))
    two=compile_native_portfolio(**(
        args|{"targets":("apple_ii","nintendo_game_boy_color"),
              "output":tmp_path/"second-run"}
    ))
    assert one["portfolio_digest"]==two["portfolio_digest"]
    assert one["native_projects"]==two["native_projects"]
    assert one["original_world_digest"]==two["original_world_digest"]


def test_portfolio_rollback_is_atomic_if_late_cartridge_cannot_fit_source_world(tmp_path):
    args=_arguments(tmp_path)
    args["width"]=25
    # Modern desktop and Apple II can accommodate this map, Game Boy cannot.
    with pytest.raises(Exception,match="budget|exceeds"):
        compile_native_portfolio(**args)
    assert not args["output"].exists()
    assert not list(tmp_path.glob(".skeleton-native-port-*"))


def test_portfolio_rejects_unsupported_or_duplicated_targets_and_no_authority(tmp_path):
    args=_arguments(tmp_path)
    with pytest.raises(PermissionError):
        compile_native_portfolio(**(args|{"authorized":False}))
    with pytest.raises(NativePortfolioError,match="real native"):
        compile_native_portfolio(**(args|{"targets":("sony_ps5",)}))
    with pytest.raises(NativePortfolioError,match="duplicate"):
        compile_native_portfolio(**(args|{"targets":("apple_ii","apple_ii")}))
    with pytest.raises(NativePortfolioError,match="tuple"):
        compile_native_portfolio(**(args|{"targets":["apple_ii"]}))
    with pytest.raises(NativePortfolioError,match="count"):
        compile_native_portfolio(**(args|{"targets":()}))
    assert not args["output"].exists()
