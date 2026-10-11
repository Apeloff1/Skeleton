"""End-to-end CLI checks for unified playable modes."""
from __future__ import annotations

import json

import pytest

from skeleton.game.generation.original_world_campaign import (
    CampaignAction, CampaignError,
)
from skeleton.game.generation.original_world_play_cli import (
    _parse_script, _parse_terminal, main,
)


@pytest.mark.parametrize("mode,world,commands", [
    ("campaign", "serenity-05",
     '[{"verb":"weave","amount":2},{"verb":"end_turn"}]'),
    ("living", "serenity-05",
     '[{"social":"greet","resident":0},{"verb":"end_turn"}]'),
    ("nexus", "serenity-05",
     '[{"verb":"weave","amount":2},{"portal":1},{"verb":"end_turn"},'
     '{"portal":2},{"verb":"redirect_rain","option":"west","amount":2}]'),
])
def test_all_modes_execute_nontrivial_sequences(
    mode: str, world: str, commands: str, capsys
) -> None:
    assert main(["--mode", mode, "--world", world,
                 "--seed", "unified", "--actions-json", commands]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mode"] == mode
    assert data["status"] == "playable-abstract"
    assert data["available_world_actions"]
    assert data["render"]
    if mode == "nexus":
        assert data["state"]["state"]["current_realm"] == 2
        assert data["state"]["state"]["realms"][0]["quilt"] == 4
        assert data["state"]["state"]["realms"][2]["rain_west"] == 8
    elif mode == "living":
        assert data["state"]["society"]["day"] == 1
        assert data["state"]["society"]["residents"][0]["trust"] == 6
    else:
        assert data["state"]["state"]["quilt"] == 4


def test_nexus_portable_inventory_roundtrip_in_real_cli(tmp_path, capsys) -> None:
    dest = tmp_path / "nexus.json"
    assert main([
        "--mode", "nexus", "--seed", "portable", "--save", str(dest),
        "--actions-json", '[{"verb":"weave","amount":2},{"portal":1}]',
    ]) == 0
    first = json.loads(capsys.readouterr().out)
    assert dest.is_file()
    assert first["state"]["state"]["realms"][0]["wood"] == 0
    assert first["state"]["state"]["realms"][1]["wood"] == 1
    assert main([
        "--mode", "nexus", "--load", str(dest),
        "--actions-json", '[{"verb":"end_turn"},{"portal":2}]',
    ]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["state"]["state"]["current_realm"] == 2
    assert sum(w["wood"] for w in second["state"]["state"]["realms"]) == 1


def test_living_mode_actual_contact_and_save(tmp_path, capsys) -> None:
    dest = tmp_path / "living.json"
    script = ('[{"social":"greet"},{"social":"invite"},'
              '{"verb":"move","target":1},{"verb":"end_turn"}]')
    assert main([
        "--mode", "living", "--world", "topology-02", "--seed", "npc",
        "--save", str(dest), "--actions-json", script,
    ]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["state"]["society"]["residents"][0]["following"] is True
    assert first["state"]["society"]["residents"][0]["location"] == 1
    assert main(["--mode", "living", "--load", str(dest),
                 "--actions-json", '[{"verb":"forage"}]']) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["state"]["campaign"]["event_count"] == (
        first["state"]["campaign"]["event_count"] + 1
    )


def test_terminal_parses_distinct_realms_and_resident_commands() -> None:
    assert _parse_terminal("portal 1", "nexus") == ("portal", 1)
    assert _parse_terminal("recharge 2", "nexus") == ("recharge", 2)
    kind, action = _parse_terminal("social greet 0 1", "living")
    assert kind == "social"
    assert action.verb == "greet" and action.resident == 0
    kind, command = _parse_terminal("move 5", "nexus")
    assert kind == "world"
    assert isinstance(command, CampaignAction) and command.target == 5
    with pytest.raises(CampaignError):
        _parse_terminal("portal nowhere", "nexus")
    with pytest.raises(CampaignError):
        _parse_terminal("social greet x", "living")


@pytest.mark.parametrize("mode,value", [
    ("campaign", '[{"social":"greet"}]'),
    ("living", '[{"portal":1}]'),
    ("nexus", '[{"social":"invite"}]'),
    ("nexus", '[{"portal":1,"amount":4}]'),
    ("nexus", '[{"recharge":2,"bonus":4}]'),
    ("living", '[{"verb":"unknown"}]'),
    ("campaign", '[{"verb":"rest","unexpected":5}]'),
    ("campaign", 'null'),
])
def test_input_is_strict_across_modes(mode: str, value: str) -> None:
    with pytest.raises(CampaignError):
        _parse_script(value, mode)


def test_interactive_nexus_expedition_and_solo_game(monkeypatch, capsys) -> None:
    instructions = iter(("weave 2", "portal 1", "end_turn", "map", "quit"))
    monkeypatch.setattr("builtins.input", lambda _: next(instructions))
    assert main(["--mode", "nexus", "--interactive"]) == 0
    output = capsys.readouterr().out
    assert "Crossed between independent original worlds" in output
    assert "World nexus: 1" in output
