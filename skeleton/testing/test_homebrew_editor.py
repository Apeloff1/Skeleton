"""Model-free, rights-locked 32x32 homebrew editing and real executable export."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.game.game_project import _demo
from scripts.game.homebrew_edit import execute_recipe, main as edit_cli
from skeleton.ai.runtime.game_rights import (
    GameRightsError, admit_game_rights, admit_homebrew_project,
)
from skeleton.ai.runtime.game_project_capsule import (
    GameCapsuleError, make_game_capsule, verify_game_capsule,
)
from skeleton.ai.runtime.homebrew_editor import (
    HomebrewEditor, HomebrewEditorError,
    OPERATOR_GUIDE, EDITOR_TOOLS, analyze_homebrew_level,
)
from skeleton.ai.runtime.gameplay_capabilities import compile_level


def original(seed=42):
    return _demo(seed, ["chip8-vip", "windows-11", "playstation-5"], "NO")


def session():
    return HomebrewEditor(original())


def recipe(c, commands, *, final_win=False):
    return {
        "schema_version": "skeleton.game.homebrew_editor_recipe.v1",
        "base_tile_sha256": c["edited_tile_sha256"],
        "batches": [{
            "commands": commands,
            "require_grid_route": True,
            "require_controller_win": False,
        }],
        "analysis_targets": ["chip8-vip", "windows-11"],
        "require_final_controller_win": final_win,
    }


def test_homebrew_only_gate_rejects_existing_games_even_with_permission_claims():
    product = original()
    rights = product["rights_manifest"]
    approved = admit_homebrew_project(
        rights, action="original_game", jurisdiction="NO",
    )
    assert approved["homebrew_only"] is True
    assert approved["existing_game_reproduction_allowed"] is False
    assert approved["asset_import_from_commercial_games_allowed"] is False
    assert approved["originality_independently_verified"] is False
    assert approved["rights_assertion_only"] is True
    for action in (
        "modify_authorized", "private_reproduction",
        "interoperability_study", "publish", "train_on_assets",
    ):
        with pytest.raises(GameRightsError, match="homebrew-only"):
            admit_homebrew_project(rights, action=action, jurisdiction="NO")
        with pytest.raises(GameCapsuleError):
            make_game_capsule(
                source_tiles=product["source_tilemap"], rights_manifest=rights,
                target_ids=["windows-11"], required_features=["tile2d"],
                action=action, jurisdiction="NO",
            )


@pytest.mark.parametrize("kind", [
    "licensed", "open_licensed", "commissioned", "public_domain_claimed",
    "interoperability_research", "user_supplied_unverified",
])
def test_homebrew_only_rejects_external_or_derivative_assets_even_if_distributable(kind):
    project = original()
    original_assets = copy.deepcopy(project["rights_manifest"])
    original_assets["assets"][0]["source_kind"] = kind
    original_assets["assets"][0]["contains_third_party_content"] = True
    original_assets["assets"][0]["allowed_uses"] = ["embed", "modify", "distribute"]
    with pytest.raises(GameRightsError, match="homebrew"):
        admit_homebrew_project(
            original_assets, action="original_game", jurisdiction="NO",
        )
    with pytest.raises(GameCapsuleError):
        make_game_capsule(
            source_tiles=project["source_tilemap"],
            rights_manifest=original_assets,
            target_ids=["windows-11"], required_features=["tile2d"],
            action="original_game", jurisdiction="NO",
        )


def test_original_project_forbids_source_game_reference_sdk_pseudopermission_and_trademark():
    base = original()
    for field, value in (
        ("source_game_reference", "commercial-title-2020"),
        ("sdk_authorization", "claim-licensed-sdk-2026"),
    ):
        manifest = copy.deepcopy(base["rights_manifest"])
        manifest[field] = value
        with pytest.raises(GameCapsuleError):
            make_game_capsule(
                source_tiles=base["source_tilemap"],
                rights_manifest=manifest, target_ids=["windows-11"],
                required_features=["tile2d"], action="original_game",
                jurisdiction="NO",
            )
    manifest = copy.deepcopy(base["rights_manifest"])
    manifest["assets"][0]["contains_trademarks"] = True
    with pytest.raises(GameRightsError):
        admit_homebrew_project(manifest, action="original_game", jurisdiction="NO")


def test_all_creative_capsules_have_explicit_homebrew_only_flags_and_recheck():
    p = original()
    assert p["homebrew_only"] is True
    assert p["third_party_game_porting_supported"] is False
    assert p["rights_receipt"]["homebrew_only"] is True
    assert verify_game_capsule(p)["homebrew_only"] is True
    p["homebrew_only"] = False
    with pytest.raises(GameCapsuleError):
        verify_game_capsule(p)


def test_editor_exposes_real_tool_contracts_not_network_plugins():
    e = session()
    cap = e.capabilities()
    assert cap["homebrew_only"] is True
    assert cap["tool_count"] == len(EDITOR_TOOLS) == len(OPERATOR_GUIDE) == 11
    assert cap["max_edited_cells"] == 1024
    assert cap["max_canvas_side"] == 32
    assert cap["undo_redo"] is True
    assert cap["third_party_game_import_allowed"] is False
    assert cap["source_rights_authorization_independently_verified"] is False
    assert cap["model_training_examples_added"] == 0
    assert e.tile_sha256 == e.source["edited_tile_sha256"]


def test_editor_brush_line_rectangle_stamp_and_flood_modify_actual_tile_geometry():
    e = session()
    init = e.tiles[:]
    x, y = 2, 2
    # Safe single-cell change away from S/G; it may equal the existing cell.
    replacement = "." if e.tiles[y][x] == "#" else "#"
    r = e.apply([{"op": "paint", "x": x, "y": y, "tile": replacement}],
                expected_tile_sha256=e.tile_sha256, require_grid_route=False)
    assert r["batch_operations"] == 1
    assert e.tiles[y][x] == replacement
    assert e.tiles != init
    assert len(e.audit_sha256) == 64
    undo = e.undo()
    assert undo == init
    redo = e.redo()
    assert redo[y][x] == replacement
    tasks = [
        {"op": "brush", "x": 2, "y": 3, "radius": 1,
         "shape": "circle", "tile": "."},
        {"op": "line", "x0": 1, "y0": 3, "x1": 5, "y1": 3,
         "tile": "."},
        {"op": "rectangle", "x0": 4, "y0": 3, "x1": 6, "y1": 5,
         "tile": ".", "filled": True},
        {"op": "stamp", "x": 4, "y": 5, "pattern": ["??.", "?#."]},
    ]
    commit = e.apply(tasks, expected_tile_sha256=e.tile_sha256,
                     require_grid_route=False)
    assert commit["commands_spent"] == 5
    assert e.tiles[3][4] == "."
    assert len(e.events) == 2
    assert e.events[1]["parent_audit_sha256"] == e.events[0]["event_sha256"]


def test_editor_noise_variants_are_reproducible_and_never_mutate_source():
    editor = session()
    source = editor.tiles[:]
    first = editor.variants(seeds=[1, 2, 42], wall_percent=25)
    second = editor.variants(seeds=[1, 2, 42], wall_percent=25)
    assert first == second
    assert len(first) == 3
    assert all(item["source_tiles_original"] and
               item["training_examples_added"] == 0 for item in first)
    assert len({tuple(item["tiles"]) for item in first}) >= 2
    assert editor.tiles == source
    assert editor.command_count == 0


def test_editor_atomic_batch_rejects_unknown_operation_and_rolls_back():
    e = session()
    previous = (e.tiles[:], e.tile_sha256, e.cursor, e.command_count)
    with pytest.raises(HomebrewEditorError):
        e.apply([
            {"op": "paint", "x": 2, "y": 3, "tile": "."},
            {"op": "execute_python", "script": "open('/tmp/a', 'w')"},
        ], expected_tile_sha256=e.tile_sha256)
    assert (e.tiles, e.tile_sha256, e.cursor, e.command_count) == previous
    assert not e.events


def test_editor_rejects_stale_sha_symlinks_raw_assets_and_invalid_geometry():
    e = session()
    before = e.tiles[:]
    with pytest.raises(HomebrewEditorError, match="optimistic-lock"):
        e.apply([{"op": "paint", "x": 2, "y": 3, "tile": "."}],
                expected_tile_sha256="f"*64)
    for mutation in (
        {"op": "paint", "x": 1, "y": 1, "tile": "#"},
        {"op": "paint", "x": -1, "y": 2, "tile": "."},
        {"op": "paint", "x": True, "y": 2, "tile": "."},
        {"op": "stamp", "x": 2, "y": 2, "pattern": ["../evil"]},
        {"op": "stamp", "x": 2, "y": 2, "pattern": ["S"]},
        {"op": "brush", "x": 2, "y": 2, "shape": "spiral",
         "radius": 1, "tile": "#"},
        {"op": "noise", "seed": "import os", "wall_percent": 30,
         "x0": 1, "y0": 1, "x1": 3, "y1": 3},
    ):
        with pytest.raises(HomebrewEditorError):
            e.apply([mutation], expected_tile_sha256=e.tile_sha256,
                    require_grid_route=False)
        assert e.tiles == before


def test_marker_relocation_undo_redo_and_full_project_export():
    e = session()
    old = compile_level({"tiles": e.tiles})["spawn"]
    new = {"x": 2, "y": 4}
    # May be wall; carve open before moving the unique marker.
    e.apply([
        {"op": "paint", "x": 2, "y": 4, "tile": "."},
        {"op": "move_marker", "marker": "S", **new},
        {"op": "carve_route", "order": "horizontal_first"},
    ], expected_tile_sha256=e.tile_sha256, require_grid_route=True)
    assert e.tiles[old["y"]][old["x"]] == "."
    assert e.tiles[new["y"]][new["x"]] == "S"
    authored = e.export_capsule()
    assert authored["source_tilemap"] == e.base
    assert authored["tilemap"] == e.tiles
    assert authored["rights_receipt"]["homebrew_only"] is True
    assert verify_game_capsule(authored)["scene_recomputed"] is True
    assert authored["training_examples_added"] == 0
    assert e.undo()[old["y"]][old["x"]] == "S"
    assert e.redo()[new["y"]][new["x"]] == "S"


def test_level_analysis_separates_grid_routes_from_real_controller_proof():
    e = session()
    analysis = e.analyze(target_ids=["chip8-vip", "game-boy", "windows-11"])
    assert analysis["tile_sha256"] == e.tile_sha256
    assert analysis["wall_tiles"] <= analysis["width"] * analysis["height"]
    assert analysis["collider_rectangles"] > 0
    assert analysis["dead_ends"] >= 0
    assert analysis["search_states"] >= 1
    assert analysis["controller_status"] in (
        "playable", "inconclusive_frame_budget",
        "inconclusive_state_budget", "unreachable_under_current_rules",
    )
    assert len(analysis["target_options"]) == 3
    assert analysis["target_options"][0]["specific_map_dimensions_fit"] is False
    assert analysis["target_options"][1]["exporter_implemented"] is False
    assert all(not t["release_approved"] for t in analysis["target_options"])


def test_homebrew_editor_recipe_roundtrips_without_overwrite_or_new_training_data(
    tmp_path: Path, capsys,
):
    p = original()
    ops = [{"op": "noise", "seed": 42, "wall_percent": 20,
            "x0": 3, "y0": 2, "x1": 6, "y1": 4},
           {"op": "carve_route", "order": "horizontal_first"}]
    request = recipe(p, ops)
    c, report = execute_recipe(p, request)
    assert verify_game_capsule(c)["homebrew_only"] is True
    assert report["commands_executed"] == 2
    assert report["homebrew_only"] is True
    assert report["training_examples_added"] == 0
    source = tmp_path / "input.json"
    tasks = tmp_path / "recipe.json"
    output = tmp_path / "new-game.json"
    source.write_text(json.dumps(p), "utf-8")
    tasks.write_text(json.dumps(request), "utf-8")
    first_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    assert edit_cli(["--capsule", str(source), "--recipe", str(tasks),
                     "--output", str(output)]) == 0
    cli_report = json.loads(capsys.readouterr().out)
    assert cli_report["new_capsule_sha256"] == c["capsule_sha256"]
    assert json.loads(output.read_text("utf-8")) == c
    assert edit_cli(["--capsule", str(source), "--recipe", str(tasks),
                     "--output", str(output)]) == 1
    assert hashlib.sha256(source.read_bytes()).hexdigest() == first_hash


def test_editor_fails_closed_on_unauthorized_attempts_to_convert_licensed_game():
    p = original()
    tampered = copy.deepcopy(p)
    tampered["action"] = "modify_authorized"
    with pytest.raises(HomebrewEditorError):
        HomebrewEditor(tampered)
    bad = copy.deepcopy(p)
    bad["rights_manifest"]["assets"][0]["source_kind"] = "licensed"
    bad["rights_manifest"]["assets"][0]["contains_third_party_content"] = True
    with pytest.raises(HomebrewEditorError):
        HomebrewEditor(bad)
