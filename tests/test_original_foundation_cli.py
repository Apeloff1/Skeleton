"""Foundation browser and interactive cross-law game CLI tests."""
from __future__ import annotations

import json

import pytest

from skeleton.game.generation.original_foundation_cli import (
    _parse_command, _parse_script, main,
)
from skeleton.game.generation.original_foundation_compiler import (
    FoundationError, STRUCTURED_FOUNDATIONS,
)


def test_reports_are_honest_about_root_vs_structured_compositions(capsys) -> None:
    assert main(["--report"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["cross_law_composed_foundation_entries"] == 10240
    assert data["total_world_foundation_entries"] == 11536
    assert data["individually_written_world_roots_total"] == 1424
    assert not data["cross_law_entries_are_individually_hand_written"]


def test_bounded_paged_world_registry_includes_two_distinct_causal_laws(capsys) -> None:
    assert main(["--page", "10237", "--limit", "16"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 3
    assert [x["index"] for x in data["worlds"]] == ["10237", "10238", "10239"]
    for law in data["worlds"]:
        assert law["id"].startswith("fnd-root-")
        assert law["root_law"]
        assert law["regime_law"]
        assert law["causal_coupling"]


def test_original_10k_worlds_actually_accept_rules_in_terminal(capsys) -> None:
    assert main([
        "--index", "9999",
        "--actions-json", '[{"verb":"intervene"},{"verb":"negotiate"},{"verb":"end_turn"}]',
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["game_state"]["tick"] == 1
    assert result["game_state"]["event_count"] == 3
    assert result["simulation_status"] == "bounded-generic-causal-prototype"
    assert result["foundation"]["provenance"] == "authored-causal-composition"


def test_interactive_causal_game_with_real_player_choices(monkeypatch, capsys) -> None:
    instructions = iter(("intervene", "study", "end_turn", "status", "quit"))
    monkeypatch.setattr("builtins.input", lambda _: next(instructions))
    assert main(["--index", "0", "--interactive"]) == 0
    output = capsys.readouterr().out
    assert "Activated causal overlay" in output
    assert "Turn 1" in output
    assert "Root" not in output  # UI reports the actual premise, not fabricated playability.


def test_world_save_restore_tracks_exact_causal_laws(tmp_path, capsys) -> None:
    path = tmp_path / "fnd-save.json"
    script = '[{"verb":"intervene"},{"verb":"end_turn"}]'
    assert main(["--index", "4023", "--actions-json", script,
                 "--save", str(path)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert path.is_file()
    assert main(["--load", str(path),
                 "--actions-json", '[{"verb":"study"}]']) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["game_state"]["event_count"] == 3
    assert second["foundation"]["foundation_id"] == first["foundation"]["foundation_id"]
    assert second["game_state"]["event_head"] != first["game_state"]["event_head"]


@pytest.mark.parametrize("bad", [
    "nope", "null", "{}", '[{"verb":"missing"}]',
    '[{"verb":"study","secret":1}]',
    '[{"verb":"intervene","amount":-1}]',
])
def test_bad_game_scripts_are_rejected_or_fail_in_step(bad) -> None:
    if bad == '[{"verb":"intervene","amount":-1}]':
        # Structural parsing leaves all state validation to the engine.
        assert _parse_script(bad)[0].amount == -1
    else:
        with pytest.raises(FoundationError):
            _parse_script(bad)


def test_player_parser_supports_directed_move_and_persistent_fork() -> None:
    assert _parse_command("move 5").target == 5
    assert _parse_command("choose care").option == "care"
    assert _parse_command("intervene 2").amount == 2
    assert _parse_command("end_turn").verb == "end_turn"
    for invalid in ("move", "move no", "choose", "intervene a", "unknown"):
        with pytest.raises(FoundationError):
            _parse_command(invalid)


def test_legacy_game_atlas_gateway_exposes_large_foundation_inventory(capsys) -> None:
    from skeleton.game.generation.original_world_cli import main as atlas_main

    assert atlas_main(["--foundation-index", "10239", "--brief"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["foundation"]["index"] == "10239"
    assert data["inventory"]["total_world_foundation_entries"] == 11536
    assert data["realization_status"] == "bounded-generic-causal-prototype"
    assert "--index 10239" in data["play_command"]
    assert "not individually handwritten" in data["warning"]

    assert atlas_main(["--foundation-seed", "cross-world-legacy"]) == 0
    another = json.loads(capsys.readouterr().out)
    assert another["foundation"]["foundation_index"].isdigit()

    # The original bespoke atlas path must remain independently addressable.
    assert atlas_main(["--index", "0", "--brief"]) == 0
    original = json.loads(capsys.readouterr().out)
    assert original["world"]["world_id"] in {"affection-01", "aging-01"} or (
        original["world"]["world_id"] != data["foundation"]["foundation_id"]
    )
