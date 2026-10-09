"""Windows destination upgrades from original game source, never title cloning."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.game.port_homebrew import main as port_cli
from skeleton.app.offline_game_preview import OfflineGamePreview
from skeleton.ai.runtime.game_rights import SCHEMA as RIGHTS_SCHEMA
from skeleton.ai.runtime.game_project_capsule import (
    make_game_capsule, verify_game_capsule, GameCapsuleError,
)
from skeleton.ai.runtime.gameplay_capabilities import compile_level
from skeleton.ai.runtime.homebrew_porting import (
    ART_DIRECTIONS, CREATIVE_MODES, HYBRID_MODES,
    HomebrewPortError, make_homebrew_port, verify_homebrew_port,
    PortedHomebrewSession, verify_port_gameplay,
)


def original(seed=42):
    original_tiles = list(OfflineGamePreview(seed=seed).tiles)
    sha = compile_level({"tiles": original_tiles})["tile_digest"]
    manifest = {
        "schema_version": RIGHTS_SCHEMA,
        "project_id": "completely-original-windows-game",
        "title": "My Original Homebrew Platform Game",
        "rights_contact": "unverified-author-of-original-tiles",
        "assets": [{
            "asset_id": "tilemap",
            "sha256": sha,
            "source_kind": "original",
            "licensor": "unverified-author-of-original-tiles",
            "license_reference": "independently-created-original-game-v1",
            "allowed_uses": ["embed", "modify"],
            "contains_third_party_content": False,
            "contains_trademarks": False,
            "contains_technological_protection": False,
        }],
        "source_game_reference": None,
        "sdk_authorization": None,
    }
    return make_game_capsule(
        source_tiles=original_tiles, rights_manifest=manifest,
        target_ids=["windows-11", "chip8-vip", "playstation-5"],
        required_features=["tile2d", "input"],
        action="original_game", jurisdiction="NO",
    )


@pytest.mark.parametrize("theme", list(ART_DIRECTIONS))
def test_all_original_styles_keep_same_physics_route_and_win(theme):
    source = original()
    enhanced = make_homebrew_port(
        source, art_direction=theme, quality="cinematic", seed=78,
        hybrids=["collectathon", "keyquest", "speedrun", "exploration", "combo"],
        scale=42, decor_budget=64,
    )
    verified = verify_homebrew_port(source, enhanced)
    won = verify_port_gameplay(source, enhanced)
    assert verified["mechanics_preserved"]
    assert won["original_gameplay_proven"] is True
    assert won["hybrid_gameplay_proven"] is True
    assert won["remaining_collectibles"] == 0
    assert won["score"] > 0
    assert won["speedrun_medal"] is True
    assert won["deterministic"] is True
    assert enhanced["render"]["pixels_per_source_tile"] == 42
    assert enhanced["source"]["source_tile_sha256"] == source["edited_tile_sha256"]
    assert enhanced["original_homebrew_only"] is True
    assert enhanced["third_party_asset_import_allowed"] is False
    assert enhanced["native_windows_package_built"] is False
    assert enhanced["legal_review_completed"] is False
    assert enhanced["training_examples_added"] == 0
    assert verify_port_gameplay(source, enhanced) == won


def test_fidelity_preserves_source_topology_collision_start_goal_and_input_trace():
    source = original()
    version = make_homebrew_port(
        source, creative_mode="enhanced_homebrew",
        art_direction="storybook", hybrids=["collectathon", "exploration"],
        scale=56,
    )
    assert version["source"]["source_capsule_sha256"] == source["capsule_sha256"]
    assert version["source"]["original_spawn"] == compile_level({"tiles": source["tilemap"]})["spawn"]
    assert version["source"]["original_goal"] == compile_level({"tiles": source["tilemap"]})["goal"]
    assert version["render"]["source_collision_map_unchanged"] is True
    assert len(version["render"]["ambient_decorations"]) == 24
    assert not version["source"]["baseline_win_trace_sha256"] == "0" * 64
    assert version["gameplay"]["exploration_fog"] is True
    assert version["gameplay"]["collectathon_score"] is True


def test_independent_clean_room_spiritual_successor_is_original_and_non_certifying():
    source = original()
    blueprint = make_homebrew_port(
        source, creative_mode="clean_room_spiritual_successor",
        art_direction="vector_celestial",
        hybrids=["keyquest", "speedrun", "combo"],
    )
    assert blueprint["creative_mode"] == "clean_room_spiritual_successor"
    assert blueprint["source_character_artwork_reused"] is False
    assert blueprint["source_music_reused"] is False
    assert blueprint["source_trademarks_reused"] is False
    assert blueprint["third_party_game_cloning_or_skin_swap_allowed"] is False
    assert blueprint["commercial_game_source_used"] is False
    assert blueprint["publish_approved"] is False
    assert verify_port_gameplay(source, blueprint)["hybrid_gameplay_proven"]
    with pytest.raises(HomebrewPortError):
        make_homebrew_port(
            source, creative_mode="clean_room_spiritual_successor",
            art_direction="pixel_heritage",
        )


def test_hybrid_runtime_keeps_state_real_and_collectibles_cannot_be_teleported():
    source = original()
    blueprint = make_homebrew_port(source, hybrids=[
        "collectathon", "keyquest", "speedrun", "exploration", "combo",
    ])
    player = PortedHomebrewSession(source, blueprint)
    before = player.snapshot()
    assert before["score"] == 0
    assert before["combo"] == 0
    assert before["visited_cells"] == 1
    assert before["remaining_items"]
    assert before["hybrid_win"] is False
    won = verify_port_gameplay(source, blueprint)
    assert won["score"] > 0
    assert won["visited_cells"] > 1
    assert won["remaining_collectibles"] == 0
    assert won["speedrun_medal"] is True
    # Actual semantics: the base physics is untouched by the hybrid UI.
    assert player.game.tiles == tuple(source["tilemap"])


@pytest.mark.parametrize("overrides", [
    {"destination": "playstation-5"},
    {"art_direction": "copyrighted-game-sprite-skin"},
    {"creative_mode": "modify_authorized"},
    {"hybrids": ["commercial_game_import"]},
    {"hybrids": ["combo", "combo"]},
    {"hybrids": ["keyquest", 42]},
    {"quality": "raytrace-movie-unsupported"},
    {"scale": True},
    {"scale": 140},
    {"decor_budget": 97},
    {"reduced_motion": "false"},
    {"seed": 2**32},
])
def test_unsupported_destinations_or_illegal_clone_modes_fail_closed(overrides):
    with pytest.raises(HomebrewPortError):
        make_homebrew_port(original(), **overrides)


def test_original_source_permission_cannot_be_replaced_by_rerehashing_port_metadata():
    source = original()
    port = make_homebrew_port(source)
    invalid = (
        lambda item: item.update({"publish_approved": True}),
        lambda item: item.update({"third_party_asset_import_allowed": True}),
        lambda item: item.update({"destination": "nintendo-switch"}),
        lambda item: item["source"].update({"original_colliders_preserved": False}),
        lambda item: item["gameplay"].update({"keyquest_gate": True}),
        lambda item: item["render"].update({"palette": ["#ff00ff"] * 5}),
    )
    for attack in invalid:
        forged = copy.deepcopy(port)
        attack(forged)
        forged["port_sha256"] = hashlib.sha256(json.dumps(
            {key: value for key, value in forged.items() if key != "port_sha256"},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")).hexdigest()
        with pytest.raises(HomebrewPortError):
            verify_homebrew_port(source, forged)


def test_commercial_title_references_cannot_enter_destination_port_even_if_labeled_homebrew():
    source = original()
    forged = copy.deepcopy(source)
    forged["rights_manifest"]["source_game_reference"] = "commercial-console-game-1985"
    with pytest.raises(HomebrewPortError):
        make_homebrew_port(forged)
    source = original()
    forged = copy.deepcopy(source)
    forged["rights_manifest"]["assets"][0]["source_kind"] = "licensed"
    forged["rights_manifest"]["assets"][0]["contains_third_party_content"] = True
    with pytest.raises(HomebrewPortError):
        make_homebrew_port(forged)


def test_accessibility_visual_toggles_have_real_render_contract_changes():
    source = original()
    default = make_homebrew_port(source)
    inclusive = make_homebrew_port(
        source, reduced_motion=True, high_contrast=True,
        colorblind_safe=True, hud=False, parallax=True,
    )
    assert default["port_sha256"] != inclusive["port_sha256"]
    assert inclusive["render"]["motion_reduced"] is True
    assert inclusive["render"]["parallax_enabled"] is False
    assert inclusive["render"]["high_contrast"] is True
    assert inclusive["render"]["colorblind_safe"] is True
    assert inclusive["render"]["hud_enabled"] is False
    assert verify_port_gameplay(source, inclusive)["hybrid_gameplay_proven"]


def test_port_cli_creates_real_verified_replay_blueprint_and_refuses_overwrite(
    tmp_path: Path, capsys,
):
    source = original()
    inp, out = tmp_path / "original.json", tmp_path / "port.json"
    inp.write_text(json.dumps(source), encoding="utf-8")
    assert port_cli([
        "--capsule", str(inp), "--output", str(out),
        "--art-direction", "storybook", "--quality", "cinematic",
        "--hybrids", "collectathon,keyquest,speedrun,exploration,combo",
        "--seed", "7", "--scale", "40", "--decor-budget", "40",
        "--high-contrast",
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["actual_hybrid_gameplay"]["hybrid_gameplay_proven"]
    assert receipt["rights_review_still_needed"] is True
    assert receipt["windows_native_executable_rebuilt"] is False
    assert receipt["output_path"] == str(out)
    assert out.exists()
    saved = json.loads(out.read_text("utf-8"))
    assert saved["art_direction"] == "storybook"
    assert verify_homebrew_port(source, saved)["mechanics_preserved"] is True
    assert port_cli([
        "--capsule", str(inp), "--verify", str(out),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["actual_hybrid_gameplay"]["hybrid_gameplay_proven"]
    assert port_cli([
        "--capsule", str(inp), "--output", str(out),
    ]) == 1
    assert "new file" in capsys.readouterr().err


def test_editor_changes_affect_destination_but_never_suggest_third_party_assets():
    from skeleton.ai.runtime.homebrew_editor import HomebrewEditor
    source = original()
    editor = HomebrewEditor(source)
    editor.apply([
        {"op": "paint", "x": 4, "y": 3, "tile": "."},
        {"op": "carve_route", "order": "horizontal_first"},
    ], expected_tile_sha256=editor.tile_sha256, require_grid_route=True)
    revised = editor.export_capsule()
    result = make_homebrew_port(
        revised, hybrids=["exploration", "speedrun"], quality="cinematic",
    )
    assert result["source"]["source_tile_sha256"] == revised["edited_tile_sha256"]
    assert result["source"]["source_capsule_sha256"] == revised["capsule_sha256"]
    assert verify_port_gameplay(revised, result)["hybrid_gameplay_proven"]
    assert result["third_party_asset_import_allowed"] is False


def test_headless_frozen_console_rechecks_real_destination_hybrid_win(
    tmp_path: Path, capsys,
):
    from skeleton.app.offline_cli import main as offline
    from skeleton.app.cli import run_app_cli
    source = original()
    blueprint = make_homebrew_port(
        source, creative_mode="hybrid_original",
        art_direction="neon_noir", quality="cinematic",
        hybrids=["collectathon", "keyquest", "speedrun", "exploration", "combo"],
    )
    original_path = tmp_path / "original.json"
    port_path = tmp_path / "enhanced.json"
    original_path.write_text(json.dumps(source), encoding="utf-8")
    port_path.write_text(json.dumps(blueprint), encoding="utf-8")
    command = [
        "--homebrew-port-check", "--homebrew-port-project", str(original_path),
        "--homebrew-port-blueprint", str(port_path), "--json",
    ]
    assert offline(command) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["hybrid_gameplay_proven"] is True
    assert receipt["original_gameplay_proven"] is True
    assert receipt["remaining_collectibles"] == 0
    assert receipt["legal_release_authorized"] is False
    assert receipt["training_examples_added"] == 0
    assert run_app_cli(["local-ai", *command]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert offline(["--homebrew-port-check", "--json"]) == 2
    assert offline(["--homebrew-port-project", str(original_path)]) == 2
    tampered = copy.deepcopy(blueprint)
    tampered["third_party_asset_import_allowed"] = True
    port_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert offline(command) == 1
    assert "rejected" in capsys.readouterr().err


def test_native_game_executable_selects_enhanced_homebrew_and_refuses_mixed_modes(
    monkeypatch,
):
    import importlib.util
    from pathlib import Path
    entrypoint = Path("packaging/windows/game_preview_entry.py").resolve()
    spec = importlib.util.spec_from_file_location("homebrew_ported_game_entry", entrypoint)
    assert spec is not None and spec.loader is not None
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    calls = []
    monkeypatch.setattr(entry, "open_native_homebrew_port",
                        lambda project, blueprint: calls.append((project, blueprint)) or 0)
    assert entry.main(["--project", "authored.json", "--port-blueprint", "port.json"]) == 0
    assert calls == [("authored.json", "port.json")]
    with pytest.raises(SystemExit) as failure:
        entry.main(["--port-blueprint", "port.json"])
    assert failure.value.code == 2
    with pytest.raises(SystemExit) as failure:
        entry.main(["--chip8-demo", "--port-blueprint", "port.json"])
    assert failure.value.code == 2


def test_native_port_ui_treats_unavailable_window_as_nonfatal_to_headless_acceptance(
    tmp_path: Path, monkeypatch,
):
    import sys
    from types import SimpleNamespace
    from skeleton.app.homebrew_port_ui import open_native_homebrew_port
    source = original()
    port = make_homebrew_port(source, hybrids=["collectathon", "exploration"])
    original_path = tmp_path / "original.json"
    port_path = tmp_path / "windows-port.json"
    original_path.write_text(json.dumps(source), encoding="utf-8")
    port_path.write_text(json.dumps(port), encoding="utf-8")
    class NoDisplay(Exception):
        pass
    def fail_root():
        raise NoDisplay()
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(
        Tk=fail_root, TclError=NoDisplay,
    ))
    with pytest.raises(HomebrewPortError, match="display"):
        open_native_homebrew_port(str(original_path), str(port_path))
    assert verify_port_gameplay(source, port)["hybrid_gameplay_proven"]
