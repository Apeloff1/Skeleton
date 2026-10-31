"""Executable original Godot expedition CLI and safe export guarantees."""
import json
from pathlib import Path
import pytest

from scripts.build_original_expedition import (
    build_original_expedition, export_new_game, main,
)
from skeleton.jeeves.game_frontier_expedition import ExpeditionError


def test_cli_builds_original_game_files_with_real_simulated_route_receipts():
    files,report=build_original_expedition("original",seed=19,islands=9)
    assert report["actual_simulated_routes"]>=2
    assert not report["native_executed"]
    assert report["native_playthrough_receipt"] is None
    assert not report["full_original_masterplan_completed"]
    assert "game/frontier/expedition.gd" in files
    assert "game/frontier/autoplay.json" in files
    assert set(report["canonical_file_hashes"])==set(files)
    assert (files,report)==build_original_expedition("original",seed=19,islands=9)


def test_cli_exports_a_complete_game_and_refuses_overwrite(tmp_path):
    files,report=build_original_expedition("game",seed=22,islands=8)
    root=tmp_path/"new_game"
    export_new_game(root,files)
    for path,content in files.items():
        assert (root/path).read_text(encoding="utf-8")==content
    with pytest.raises(ExpeditionError,match="exists"):
        export_new_game(root,files)
    assert "EXPEDITION_READY" in (root/"game/frontier/expedition.gd").read_text()


def test_cli_refuses_path_traversal_and_leaves_no_project(tmp_path):
    root=tmp_path/"unsafe"
    with pytest.raises(ExpeditionError,match="unsafe"):
        export_new_game(root,{"../overwrite":"attack"})
    assert not root.exists()
    assert not (tmp_path/"overwrite").exists()


@pytest.mark.parametrize("seed,islands",((1,3),(9,8),(413,16)))
def test_multiple_seeded_original_projects_are_independent(seed,islands):
    a,b=build_original_expedition("original",seed=seed,islands=islands)
    assert b["waypoint_count"]>=islands
    assert b["connected_edges"]>=islands
    assert len(b["route_playthrough_receipt"])==64


def test_cli_rejects_bad_authoring_counts():
    with pytest.raises(ExpeditionError,match="islands"):
        build_original_expedition("game",seed=8,islands=0)


def test_no_native_silent_success_without_real_godot():
    with pytest.raises(ExpeditionError,match="does not exist"):
        build_original_expedition(
            "game",seed=1,islands=4,native=True,
            godot_executable="/not/an/engine",
        )


def test_main_emits_valid_report_with_explicit_simulated_proof(capsys):
    assert main(["--project-id","campaign","--seed","7","--islands","5"])==0
    report=json.loads(capsys.readouterr().out)
    assert report["project_id"]=="campaign"
    assert report["actual_simulated_routes"]>0
    assert not report["native_executed"]
