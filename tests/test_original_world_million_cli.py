"""Million-configuration game CLI smoke: exact indexes, modes, arcs, saves."""
from __future__ import annotations

import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_million_cli import (
    main, parse_advanced_command, parse_advanced_script,
)


def test_inventory_exposes_1m_without_fake_bespoke_games(capsys) -> None:
    assert main(["--inventory"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mechanically_mode_bound_foundation_entries"] == 102400
    assert data["advanced_structured_configuration_entries"] == 1228800
    assert data["individually_handwritten_advanced_worlds"] == 0
    assert data["fully_native_verified_games"] == 0


def test_page_at_final_edge_without_mass_materialization(capsys) -> None:
    assert main(["--page", "1228798", "--limit", "32"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["total"] == "1228800"
    assert [x["index"] for x in data["entries"]] == ["1228798", "1228799"]
    assert all(x["provenance"] == "composed-authored-laws-with-executable-modes"
               for x in data["entries"])


def test_exact_controlled_game_selection_allows_real_mode_play(capsys) -> None:
    assert main([
        "--base", "10239", "--form", "puzzle", "--arc", "chapters",
        "--actions-json", '[{"layer":"mode","verb":"toggle","target":0},'
                          '{"layer":"mode","verb":"toggle","target":2},'
                          '{"layer":"mode","verb":"pass"},'
                          '{"layer":"arc","verb":"commit"}]',
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["configuration"]["mode"]["base_index"] == "10239"
    assert result["configuration"]["mode"]["form"]["form_id"] == "puzzle"
    assert result["configuration"]["arc"]["arc_id"] == "chapters"
    assert result["game"]["mode"]["cleared"] is True
    assert result["game"]["arc"]["completed"] is True
    assert result["game"]["events"] == 4
    assert result["status"] == "bounded-reference-game"


def test_scripted_game_saves_and_resumes_immutable_history(tmp_path, capsys) -> None:
    path = tmp_path / "million.json"
    assert main([
        "--base", "0", "--form", "tactics", "--arc", "dynasty",
        "--actions-json", '[{"layer":"mode","verb":"guard"},'
                          '{"layer":"mode","verb":"strike"}]',
        "--save", str(path),
    ]) == 0
    prior = json.loads(capsys.readouterr().out)
    assert path.is_file()
    assert main([
        "--load", str(path),
        "--actions-json", '[{"layer":"causal","verb":"end_turn"}]',
    ]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["game"]["events"] == prior["game"]["events"] + 1
    assert again["game"]["causal"]["payload"]["state"]["tick"] == 1


def test_playable_endless_persists_without_fake_win(capsys) -> None:
    assert main([
        "--base", "0", "--form", "puzzle", "--arc", "endless",
        "--actions-json", '[{"layer":"mode","verb":"toggle","target":0},'
                          '{"layer":"mode","verb":"toggle","target":2},'
                          '{"layer":"mode","verb":"pass"},'
                          '{"layer":"causal","verb":"end_turn"}]',
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["game"]["mode"]["cleared"] is True
    assert result["game"]["arc"]["completed"] is False
    assert result["configuration"]["arc"]["continuation_policy"] == "unwinnable"


def test_terminal_parser_separates_commands_correctly() -> None:
    assert parse_advanced_command("mode jump 2").amount == 2
    assert parse_advanced_command("mode toggle 2").target == 2
    assert parse_advanced_command("mode tap 0").target == 0
    assert parse_advanced_command("arc choose power").option == "power"
    assert parse_advanced_command("causal end_turn").verb == "end_turn"
    assert len(parse_advanced_script(
        '[{"layer":"mode","verb":"jump"},'
        '{"layer":"arc","verb":"reflect"},'
        '{"layer":"causal","verb":"end_turn"}]',
    )) == 3
    for invalid in ("unknown", "mode toggle", "arc choose", "mode jump not-a-number"):
        with pytest.raises(FoundationError):
            parse_advanced_command(invalid)


def test_interactive_genre_session(monkeypatch, capsys) -> None:
    instructions = iter(("mode toggle 0", "mode toggle 2", "mode pass",
                         "arc commit", "status", "quit"))
    monkeypatch.setattr("builtins.input", lambda _: next(instructions))
    assert main([
        "--base", "0", "--form", "puzzle", "--arc", "chapters",
        "--interactive",
    ]) == 0
    lines = capsys.readouterr().out
    assert "Genre objective completed" in lines
    assert "Original Million-World Forge" in lines
    assert "arc completed" in lines


@pytest.mark.parametrize("invalid", (
    'null', "{}", "not-json",
    '[{"layer":"missing","verb":"jump"}]',
    '[{"layer":"mode","verb":"jump","unknown":1}]',
))
def test_untrusted_script_rejected(invalid) -> None:
    with pytest.raises(FoundationError):
        parse_advanced_script(invalid)


def test_invalid_selectors_raise_real_cli_error(capsys) -> None:
    with pytest.raises(SystemExit):
        main(["--base", "3", "--form", "puzzle"])
    with pytest.raises(SystemExit):
        main(["--index", "1228800"])
    with pytest.raises(SystemExit):
        main(["--page", "12", "--index", "33"])
