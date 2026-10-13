"""Actual controller-movement validation, not just connected tilemaps."""
from __future__ import annotations

import hashlib
import json

import pytest

from skeleton.ai.runtime.game_playability import (
    MAX_SEARCH_FRAMES, MAX_STATES, check_game_playability,
)
from skeleton.ai.runtime.gameplay_capabilities import (
    GameplayError, compile_level, platformer_replay,
)
from skeleton.ai.runtime.deterministic_capabilities import (
    execute_capability_task,
)

MAP = [
    "########",
    "#S.....#",
    "#...#..#",
    "#......#",
    "#......#",
    "#......#",
    "#......#",
    "#.....G#",
    "########",
]


def test_controller_search_finds_real_winning_game_and_matches_replay():
    outcome = check_game_playability({"tiles": MAP, "max_frames": 96})
    assert outcome["status"] == "playable"
    assert outcome["playable_under_integer_platformer_rules"] is True
    assert 1 <= outcome["controller_frames"] <= 96
    assert outcome["controller_frames"] == len(outcome["controller_actions"])
    replay = platformer_replay({
        "tiles": MAP,
        "avatar": {"x": 1, "y": 1, "vx": 0, "vy": 0},
        "controls": outcome["controller_actions"],
    })
    assert replay["goal_first_reached_frame"] == outcome["controller_frames"]
    assert outcome["model_inference_used"] is False
    assert outcome["training_examples_added"] == 0
    assert outcome["console_hardware_validated"] is False
    assert check_game_playability({"tiles": MAP, "max_frames": 96}) == outcome


def test_real_playability_is_independent_of_abstract_grid_reachability():
    # The goal may be topologically connected, but not reachable by the
    # specific primitive within one horizontal step.
    assert compile_level({"tiles": MAP})["goal_reachable"] is True
    limited = check_game_playability({"tiles": MAP, "max_frames": 1})
    assert limited["playable_under_integer_platformer_rules"] is False
    assert limited["controller_actions"] == []
    assert limited["status"] in (
        "inconclusive_frame_budget", "unreachable_under_current_rules",
    )


@pytest.mark.parametrize("budget", [-1, 0, 97, True, 1.1, "64"])
def test_unbounded_or_malformed_gameplay_search_is_rejected(budget):
    with pytest.raises(GameplayError):
        check_game_playability({"tiles": MAP, "max_frames": budget})


def test_search_refuses_arbitrary_codes_or_untrusted_callbacks():
    with pytest.raises(GameplayError):
        check_game_playability({
            "tiles": MAP, "max_frames": 32, "callback": "__import__('os')",
        })


def test_gameplay_search_exposed_in_pure_typed_operation_catalog():
    receipt = execute_capability_task({
        "operation": "game.playability_check",
        "args": {"tiles": MAP, "max_frames": 96},
    })
    assert receipt["operation"] == "game.playability_check"
    assert receipt["result"]["status"] == "playable"
    assert receipt["model_inference_used"] is False
    assert len(receipt["result_sha256"]) == 64


def test_transient_frame_limit_never_claims_game_is_logically_impossible():
    source = check_game_playability({"tiles": MAP, "max_frames": 1})
    assert source["status"] != "playable"
    assert source["status"] != "game_impossible"
    assert source["search_frame_limit"] == 1
    assert source["console_hardware_validated"] is False


def test_solver_has_explicit_platform_independent_resource_caps():
    assert MAX_SEARCH_FRAMES == 96
    assert MAX_STATES == 12000
    result = check_game_playability({"tiles": MAP, "max_frames": 96})
    assert result["states_explored"] <= MAX_STATES
    assert result["transitions_evaluated"] <= MAX_STATES * 6
    assert len(json.dumps(result)) < 32768


def test_authorized_capsule_may_be_played_in_native_preview_without_assets(
    tmp_path, capsys,
):
    from skeleton.app.offline_game_preview import (
        OfflineGamePreview, load_game_project, verify_game_preview,
    )
    from skeleton.ai.runtime.game_project_capsule import make_game_capsule
    from skeleton.ai.runtime.game_rights import SCHEMA as RIGHTS_SCHEMA
    from skeleton.app.offline_cli import main as console
    from skeleton.app.cli import run_app_cli

    source = list(OfflineGamePreview(seed=42).tiles)
    sha = compile_level({"tiles": source})["tile_digest"]
    rights = {
        "schema_version": RIGHTS_SCHEMA,
        "project_id": "verified-platformer",
        "title": "Private authored game, original tiles",
        "rights_contact": "operator-unverified",
        "assets": [{
            "asset_id": "tilemap",
            "sha256": sha,
            "source_kind": "original",
            "licensor": "operator-unverified",
            "license_reference": "original-procedural-private-game",
            "allowed_uses": ["embed", "modify"],
            "contains_third_party_content": False,
            "contains_trademarks": False,
            "contains_technological_protection": False,
        }],
        "source_game_reference": None,
        "sdk_authorization": None,
    }
    capsule = make_game_capsule(
        source_tiles=source, rights_manifest=rights,
        target_ids=["windows-11", "game-boy", "playstation-5"],
        required_features=["tile2d", "input"],
        action="original_game", jurisdiction="NO",
    )
    assert capsule["playability"]["actual_controller_replay_qualified"] is True
    project = tmp_path / "private-project.json"
    project.write_text(json.dumps(capsule), encoding="utf-8")
    assert load_game_project(project) == source
    game = OfflineGamePreview(project_tiles=source)
    assert game.snapshot().tiles == tuple(source)
    proof = verify_game_preview(project_tiles=source)
    assert proof["terminal_won"] is True
    assert proof["project_source"] == "verified_portable_capsule"
    assert proof["seed"] is None
    assert proof["training_examples_added"] == 0
    assert console([
        "--game-preview-check", "--game-project", str(project), "--json",
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == proof
    assert run_app_cli([
        "local-ai", "--game-preview-check", "--game-project",
        str(project), "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == proof
    assert console([
        "--game-preview-check", "--game-project", str(project),
        "--game-seed", "42", "--json",
    ]) == 2
    assert console(["--game-project", str(project)]) == 2


def test_modified_game_files_must_pass_integrity_before_native_preview(
    tmp_path, capsys,
):
    from skeleton.app.offline_game_preview import OfflineGamePreview, load_game_project
    from skeleton.ai.runtime.game_project_capsule import make_game_capsule
    from skeleton.ai.runtime.game_rights import SCHEMA as RIGHTS_SCHEMA
    from skeleton.app.offline_cli import main

    level = list(OfflineGamePreview(seed=7).tiles)
    rights = {
        "schema_version": RIGHTS_SCHEMA,
        "project_id": "authored-level",
        "title": "Original game",
        "rights_contact": "operator-unverified",
        "assets": [{
            "asset_id": "tilemap",
            "sha256": compile_level({"tiles": level})["tile_digest"],
            "source_kind": "original", "licensor": "operator-unverified",
            "license_reference": "private-work-2026",
            "allowed_uses": ["embed", "modify"],
            "contains_third_party_content": False,
            "contains_trademarks": False,
            "contains_technological_protection": False,
        }],
        "source_game_reference": None,
        "sdk_authorization": None,
    }
    capsule = make_game_capsule(
        source_tiles=level, rights_manifest=rights,
        target_ids=["windows-11"], required_features=["tile2d"],
        action="original_game", jurisdiction="NO",
    )
    capsule["scene"]["entities"][0]["position"]["x"] = 0
    source = tmp_path / "tampered.json"
    source.write_text(json.dumps(capsule), encoding="utf-8")
    from skeleton.ai.runtime.gameplay_capabilities import GameplayError
    with pytest.raises(GameplayError):
        load_game_project(source)
    assert main([
        "--game-preview-check", "--game-project", str(source), "--json",
    ]) == 1
    assert capsys.readouterr().out == ""
