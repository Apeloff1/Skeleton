"""Executable CLI for era, cosmology and chronology choices."""
from __future__ import annotations

import json

import pytest

from skeleton.game.generation.original_world_campaign import CampaignError
from skeleton.game.generation.original_world_era_cli import (
    _parse_command, _parse_script, main,
)


def test_era_cli_uses_actual_metallurgy_costs(capsys) -> None:
    assert main([
        "--world", "serenity-05", "--era", "iron-age",
        "--actions-json", '[{"tech":"smelt"}]',
    ]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["technology"]["metal"] == 1
    assert data["event_count"] == 1
    assert data["styling"]["era"] == "iron-age"


def test_ritual_is_permitted_only_in_suitable_invented_cosmology(capsys) -> None:
    assert main([
        "--world", "serenity-05", "--theology", "faith-as-power",
        "--actions-json", '[{"ritual":"weather_invocation"}]',
    ]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["theology"]["devotion"] == 1
    assert data["event_count"] == 1
    with pytest.raises(SystemExit):
        main([
            "--world", "serenity-05", "--theology", "atheist-world",
            "--actions-json", '[{"ritual":"weather_invocation"}]',
        ])


def test_time_loop_maintains_history_with_real_phase_reset(capsys) -> None:
    actions = json.dumps([{"verb":"end_turn"} for _ in range(8)])
    assert main([
        "--world", "topology-02", "--chronology", "time-loop",
        "--actions-json", actions,
    ]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["chronology"]["turn"] == 8
    assert data["chronology"]["loops"] == 1
    assert data["event_count"] == 8


def test_styled_save_then_resume_preserves_era_and_provenance(tmp_path, capsys) -> None:
    path = tmp_path / "era.json"
    assert main([
        "--era", "iron-age", "--theology", "ancestor-veneration",
        "--actions-json", '[{"tech":"smelt"}]',
        "--save", str(path),
    ]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main([
        "--load", str(path),
        "--actions-json", '[{"ritual":"reflection"}]',
    ]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["technology"]["metal"] == first["technology"]["metal"]
    assert second["styling"]["era"] == "iron-age"
    assert second["event_count"] == 2


def test_command_parser_distinguishes_world_tech_and_ritual() -> None:
    assert _parse_command("tech smelt").verb == "smelt"
    assert _parse_command("ritual reflection").verb == "reflection"
    assert _parse_command("forage 2").verb == "forage"
    assert len(_parse_script(
        '[{"tech":"knap"},{"ritual":"communal_rite"},{"verb":"end_turn"}]'
    )) == 3
    for value in ("invalid", "{}", 'null', '[{"tech":"unknown"}]',
                  '[{"ritual":"oracle","unexpected":1}]'):
        with pytest.raises(CampaignError):
            _parse_script(value)


def test_interactive_era_actions(monkeypatch, capsys) -> None:
    instructions = iter(("tech smelt", "end_turn", "map", "quit"))
    monkeypatch.setattr("builtins.input", lambda _: next(instructions))
    assert main(["--era", "iron-age", "--interactive"]) == 0
    output = capsys.readouterr().out
    assert "Produced metal" in output
    assert "Metal 1" in output
