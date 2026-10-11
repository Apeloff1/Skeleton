"""Offline 12.288m world previews, transit and persistence smoke checks."""
from __future__ import annotations

import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_tenfold_cli import (
    main, parse_command, script_actions,
)


def test_inventory_and_final_paged_worlds_without_preallocation(capsys) -> None:
    assert main(["--inventory"]) == 0
    inventory = json.loads(capsys.readouterr().out)
    assert inventory["spatial_gameplay_foundation_entries"] == 1_024_000
    assert inventory["full_gameplay_configuration_entries"] == 12_288_000
    assert inventory["native_games_certified"] == 0
    assert main(["--page", "12287998", "--limit", "5"]) == 0
    tail = json.loads(capsys.readouterr().out)
    assert tail["size"] == "12288000"
    assert [item["index"] for item in tail["entries"]] == [
        "12287998", "12287999",
    ]


def test_selected_lattice_play_has_actual_shared_gameplay_and_materials(capsys) -> None:
    actions = json.dumps([
        {"layer": "spatial", "verb": "extract", "amount": 2},
        {"layer": "spatial", "verb": "travel", "target": 1},
        {"layer": "mode", "verb": "toggle", "target": 0},
        {"layer": "causal", "verb": "end_turn"},
    ])
    assert main([
        "--base", "0", "--form", "puzzle",
        "--architecture", "lattice", "--arc", "endless",
        "--actions-json", actions,
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["world"]["spatial"]["architecture"]["id"] == "lattice"
    assert result["state"]["space"]["position"] == 1
    assert result["state"]["space"]["materials"] == 10
    assert result["state"]["nested"]["payload"]["mode"]["switches"] == 1
    assert result["state"]["nested"]["payload"]["causal"]["payload"]["state"]["tick"] == 1
    assert result["implementation_status"] == "bounded-spatial-genre-simulation"


def test_time_varying_phase_world_and_original_game_work_together(capsys) -> None:
    assert main([
        "--base", "4", "--form", "puzzle", "--architecture", "phase",
        "--arc", "branching",
        "--actions-json", '[{"layer":"spatial","verb":"stabilize"},'
                          '{"layer":"mode","verb":"toggle","target":0},'
                          '{"layer":"causal","verb":"end_turn"}]',
        "--show-map",
    ]) == 0
    output = capsys.readouterr().out
    assert "The Reconfiguring City" in output
    assert "original" in output.lower()
    assert "stabilize" in output


def test_disk_save_resume_preserves_nested_rulebook_and_spatial_hazards(
    tmp_path, capsys
) -> None:
    save = tmp_path / "game-spatial.json"
    assert main([
        "--base", "1", "--form", "tactics", "--architecture", "archipelago",
        "--arc", "rescue",
        "--actions-json", '[{"layer":"spatial","verb":"ferry"},'
                          '{"layer":"mode","verb":"guard"}]',
        "--save", str(save),
    ]) == 0
    first = json.loads(capsys.readouterr().out)
    assert save.exists()
    assert main([
        "--load", str(save),
        "--actions-json", '[{"layer":"causal","verb":"end_turn"}]',
    ]) == 0
    last = json.loads(capsys.readouterr().out)
    assert last["state"]["space"]["ferries"] == 1
    assert last["world"]["design_id"] == first["world"]["design_id"]
    assert last["state"]["space"]["tick"] == 1
    assert last["state"]["space"]["events"] == first["state"]["space"]["events"] + 1


def test_interactive_terminal_with_real_movement_and_game_action(
    capsys, monkeypatch
) -> None:
    commands = iter((
        "spatial pave", "spatial travel 1", "mode toggle 0",
        "causal end_turn", "status", "quit",
    ))
    monkeypatch.setattr("builtins.input", lambda _: next(commands))
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--arc", "sandbox", "--interactive",
    ]) == 0
    output = capsys.readouterr().out
    assert "Original Tenfold World Forge" in output
    assert "Installed 1 real lattice improvement" in output
    assert "Spatial node 1/23" in output
    assert "Turn 1" in output


def test_cli_direct_input_parser_and_untrusted_script_validation() -> None:
    assert parse_command("spatial travel 6").target == 6
    assert parse_command("mode toggle 0").target == 0
    assert parse_command("arc choose care").option == "care"
    assert parse_command("causal end_turn").verb == "end_turn"
    assert parse_command("spatial extract 2").amount == 2
    assert len(script_actions(
        '[{"layer":"spatial","verb":"extract"},'
        '{"layer":"mode","verb":"tap","target":0}]',
    )) == 2
    for invalid in ("not-json", "null", "{}", '[{"layer":"other","verb":"rest"}]',
                    '[{"layer":"spatial","verb":"rest","secret":"x"}]'):
        with pytest.raises(FoundationError):
            script_actions(invalid)


def test_illegal_selector_combinations_refuse_to_fabricate_worlds() -> None:
    with pytest.raises(SystemExit):
        main(["--base", "0", "--form", "puzzle"])
    with pytest.raises(SystemExit):
        main(["--index", "12288000"])
    with pytest.raises(SystemExit):
        main(["--page", "5", "--seed", "colliding"])
