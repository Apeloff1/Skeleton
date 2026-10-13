"""Frontier CLI: scripted, interactive, and persistent travel tests."""
from __future__ import annotations

import json

import pytest

from skeleton.game.generation.original_world_frontier import FrontierError
from skeleton.game.generation.original_world_frontier_cli import (
    main, parse_command, parse_script,
)


def test_parse_actions_with_strict_fields_and_bounded_quantities() -> None:
    assert parse_command("move north").option == "north"
    assert parse_command("forage 2").amount == 2
    assert parse_command("end_turn").verb == "end_turn"
    assert len(parse_script(
        '[{"verb":"forage","amount":2},{"verb":"move","option":"east"}]'
    )) == 2
    for raw in ("invalid", "null", "{}", '[{"verb":"not_an_action"}]',
                '[{"verb":"rest","extra":2}]'):
        with pytest.raises(FrontierError):
            parse_script(raw)
    for raw in ("move", "move east many", "forage nan", "unknown"):
        with pytest.raises(FrontierError):
            parse_command(raw)


def test_scripted_frontier_persists_file_and_resumes_after_reopening(
    tmp_path, capsys
) -> None:
    save = tmp_path / "open_world.sqlite3"
    script = ('[{"verb":"forage","amount":2},'
              '{"verb":"move","option":"east"},'
              '{"verb":"end_turn"}]')
    assert main(["--db", str(save), "--world", "serenity-05",
                 "--seed", "world", "--actions-json", script]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "playable-sparse-frontier"
    assert first["player"]["x"] == 1
    assert first["visited"] == 2
    assert first["modified_tiles"] == 1
    assert save.is_file()
    assert main(["--db", str(save), "--world", "serenity-05",
                 "--seed", "world", "--actions-json",
                 '[{"verb":"move","option":"east"}]']) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["player"]["x"] == 2
    assert second["visited"] == 3
    assert second["player"]["event_count"] == first["player"]["event_count"] + 1


@pytest.mark.parametrize("world,actions", [
    ("topology-02", '[{"verb":"move","option":"north"},{"verb":"end_turn"}]'),
    ("ecology-03", '[{"verb":"redirect_rain","option":"west"},{"verb":"end_turn"}]'),
    ("civilization-01", '[{"verb":"pledge"},{"verb":"fulfill"},{"verb":"settle"}]'),
    ("serenity-05", '[{"verb":"weave","amount":2},{"verb":"rest"}]'),
])
def test_four_world_laws_can_be_played_from_cli(world, actions, capsys) -> None:
    assert main(["--world", world, "--seed", "run",
                 "--actions-json", actions]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["world_id"] == world
    assert data["receipts"]
    assert data["player"]["event_count"] == len(data["receipts"])


def test_interactive_expedition(monkeypatch, capsys) -> None:
    instructions = iter(("forage 2", "move east", "end_turn", "map", "quit"))
    monkeypatch.setattr("builtins.input", lambda _: next(instructions))
    assert main(["--world", "serenity-05", "--interactive"]) == 0
    output = capsys.readouterr().out
    assert "Harvested finite local material" in output
    assert "Traveled to another generated sector" in output
    assert "Turn 1" in output
