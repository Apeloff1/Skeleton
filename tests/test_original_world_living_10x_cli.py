"""Living-world studio: 122.88m inventory, scripted gameplay and persistence."""
from __future__ import annotations
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_10x_cli import (
    main, parse_script, parse_command,
)


def test_inventory_counts_rules_not_visuals_or_fictional_bespoke_games(capsys) -> None:
    assert main(["--inventory"]) == 0
    items = json.loads(capsys.readouterr().out)
    assert items["living_foundations"] == 10_240_000
    assert items["living_advanced_configurations"] == 122_880_000
    assert items["authored_living_world_systems"] == 10
    assert items["authored_living_player_interventions"] == 30
    assert items["worlds_individually_handwritten_by_composition"] == 0
    assert items["certified_native_games"] == 0


def test_paging_final_worlds_is_lazy_and_canonical(capsys) -> None:
    assert main(["--page", "122879997", "--limit", "32"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == "122880000"
    assert [w["index"] for w in payload["worlds"]] == [
        "122879997", "122879998", "122879999",
    ]
    assert payload["worlds"][-1]["system"] == "echoes"


def test_exact_living_selector_changes_simulation_and_nested_world_turn(capsys) -> None:
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--system", "trophic", "--arc", "endless",
        "--actions-json", '[{"layer":"living","verb":"graze","amount":2},'
                          '{"layer":"spatial","verb":"travel","target":1},'
                          '{"layer":"mode","verb":"toggle","target":0},'
                          '{"layer":"causal","verb":"end_turn"}]',
    ]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["world"]["foundation"]["system"] == "trophic"
    state = data["world_state"]
    assert state["living_turns"] == 1
    assert state["metrics"]["grazers"] > 0
    assert state["spatial"]["payload"]["space"]["position"] == 1
    assert state["spatial"]["payload"]["nested"]["payload"]["mode"]["switches"] == 1
    assert data["implementation_status"] == "bounded-autonomous-world-simulation"


def test_knowledge_can_educate_after_earned_verified_research(capsys) -> None:
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "phase",
        "--system", "knowledge", "--arc", "mystery",
        "--actions-json", '[{"layer":"living","verb":"observe"},'
                          '{"layer":"living","verb":"verify"},'
                          '{"layer":"living","verb":"teach"},'
                          '{"layer":"causal","verb":"end_turn"}]',
    ]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["world_state"]["metrics"]["shared"] >= 2
    assert data["world_state"]["metrics"]["proven"] == 0


def test_living_save_resume_preserves_actor_timers_and_game_state(tmp_path, capsys) -> None:
    save = tmp_path / "living-world.json"
    assert main([
        "--base", "0", "--form", "survival", "--architecture", "archipelago",
        "--system", "caravans", "--arc", "dynasty",
        "--actions-json", '[{"layer":"living","verb":"dispatch"},'
                          '{"layer":"causal","verb":"end_turn"}]',
        "--save", str(save),
    ]) == 0
    earlier = json.loads(capsys.readouterr().out)
    assert earlier["world_state"]["metrics"]["in_transit"] == 1
    assert save.is_file()
    assert main([
        "--load", str(save),
        "--actions-json", '[{"layer":"causal","verb":"end_turn"},'
                          '{"layer":"living","verb":"unload"}]',
    ]) == 0
    after = json.loads(capsys.readouterr().out)
    assert after["world"]["design_id"] == earlier["world"]["design_id"]
    assert after["world_state"]["metrics"]["in_transit"] == 0
    assert after["world_state"]["metrics"]["delivered"] == 0
    assert after["world_state"]["metrics"]["credit"] == 10


def test_interactive_living_world_supports_real_player_choice(monkeypatch, capsys) -> None:
    commands = iter(("living reseed", "spatial travel 1", "mode toggle 0",
                     "causal end_turn", "status", "quit"))
    monkeypatch.setattr("builtins.input", lambda _: next(commands))
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--system", "trophic", "--arc", "sandbox",
        "--interactive",
    ]) == 0
    display = capsys.readouterr().out
    assert "Living Original World Studio" in display
    assert "Food web advanced" in display
    assert "World tick 1" in display
    assert "position 1/23" in display


def test_valid_direct_commands_and_bounded_json_parser() -> None:
    assert parse_command("living reseed 2").amount == 2
    assert parse_command("spatial travel 3").target == 3
    assert parse_command("arc choose care").option == "care"
    assert parse_command("causal end_turn").verb == "end_turn"
    assert len(parse_script('[{"layer":"living","verb":"reseed"},'
                            '{"layer":"causal","verb":"end_turn"}]')) == 2
    for bad in ("{}", "null", "not-json",
                '[{"layer":"no-such-layer","verb":"resupply"}]',
                '[{"layer":"living","verb":"reseed","secret":"token"}]',
                '[{"layer":"living","verb":"reseed","amount":true}]'):
        with pytest.raises(FoundationError):
            parse_script(bad)


def test_invalid_index_or_unqualified_customization_fails_closed() -> None:
    with pytest.raises(SystemExit):
        main(["--index", "122880000"])
    with pytest.raises(SystemExit):
        main(["--base", "0", "--form", "puzzle", "--system", "spores"])
    with pytest.raises(SystemExit):
        main(["--page", "2", "--seed", "conflict"])
