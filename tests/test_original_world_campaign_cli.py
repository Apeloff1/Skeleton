"""CLI tests exercise terminal commands, saved state and valid preview scripts."""
from __future__ import annotations

import json

import pytest

from skeleton.game.generation.original_world_campaign import (
    CampaignError, create_campaign, import_save,
)
from skeleton.game.generation.original_world_campaign_cli import (
    _parse_terminal, main, parse_script, render,
)


def test_render_shows_visitability_and_player_resources() -> None:
    s = create_campaign("serenity-05")
    text = render(s)
    assert "@00" in text
    assert "?11" in text
    assert "Energy" in text
    assert "Postgame" not in text


def test_terminal_parser_decodes_target_mode_and_quantity() -> None:
    assert _parse_terminal("move 5").target == 5
    assert _parse_terminal("trade buy_food 2").option == "buy_food"
    assert _parse_terminal("redirect_rain west 3").amount == 3
    assert _parse_terminal("forage 2").amount == 2
    assert _parse_terminal("end_turn").verb == "end_turn"
    with pytest.raises(CampaignError):
        _parse_terminal("unknown")
    with pytest.raises(CampaignError):
        _parse_terminal("move not-a-number")
    with pytest.raises(CampaignError):
        _parse_terminal("trade")


def test_script_validation_is_fail_closed() -> None:
    assert len(parse_script('[{"verb":"forage","amount":2},{"verb":"end_turn"}]')) == 2
    for bad in (
        "null", '"forage"', "{}", "{", '[{"verb":"missing"}]',
        '[{"verb":"forage","surprise":1}]',
        '[{"verb":"forage"},{"verb":"forage"}' ,
    ):
        with pytest.raises(CampaignError):
            parse_script(bad)
    with pytest.raises(CampaignError):
        parse_script("x" * 65537)
    with pytest.raises(CampaignError):
        parse_script("[]".replace("[]", "[" + ",".join('{"verb":"rest"}' for _ in range(1025)) + "]"))


@pytest.mark.parametrize("world,script", [
    ("topology-02", '[{"verb":"observe"},{"verb":"end_turn"},{"verb":"move","target":1}]'),
    ("ecology-03", '[{"verb":"redirect_rain","option":"west","amount":2},{"verb":"end_turn"}]'),
    ("civilization-01", '[{"verb":"pledge"},{"verb":"fulfill"},{"verb":"end_turn"}]'),
    ("serenity-05", '[{"verb":"weave","amount":2},{"verb":"rest"},{"verb":"end_turn"}]'),
])
def test_each_world_has_a_real_cli_journey(
    world: str, script: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--world", world, "--seed", "cli", "--actions-json", script]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["status"] == "playable-abstract-4-worlds"
    assert view["state"]["event_count"] == len(parse_script(script))
    assert view["state"]["turn"] == 1
    assert view["available_actions"]


def test_save_and_resume_without_changing_causal_identity(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    dest = tmp_path / "campaign.json"
    assert main(["--world", "serenity-05", "--seed", "recover",
                 "--actions-json", '[{"verb":"weave","amount":2}]',
                 "--save", str(dest)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert dest.is_file()
    loaded = import_save(dest.read_text(encoding="utf-8"))
    assert loaded.event_count == 1
    assert main(["--load", str(dest),
                 "--actions-json", '[{"verb":"rest"}]']) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["state"]["event_count"] == 2
    assert second["state"]["quilt"] == first["state"]["quilt"]
    assert second["state"]["event_head"] != first["state"]["event_head"]


def test_interactive_terminal_supports_real_player_commands(monkeypatch, capsys) -> None:
    instructions = iter(("forage 2", "end_turn", "map", "quit"))
    monkeypatch.setattr("builtins.input", lambda _: next(instructions))
    assert main(["--world", "serenity-05", "--interactive"]) == 0
    output = capsys.readouterr().out
    assert "Collected 2 food" in output
    assert "Advanced the seasonally simulated world" in output
    assert "Turn: 1" in output
