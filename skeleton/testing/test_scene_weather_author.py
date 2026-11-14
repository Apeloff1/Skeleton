"""Source-fenced weather authoring, collision and replay acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    normalize_weather, original_weather_demo, verify_session,
)
from skeleton.game.gameplay.scene_weather_author import (
    edit_weather, original_authoring_demo, verify_edit,
)


def test_weather_cycle_edit_changes_real_route_and_keeps_source_immutable():
    source, _ = original_weather_demo()
    before = copy.deepcopy(source)
    receipt = original_authoring_demo()
    assert source == before
    assert receipt["before_digest"] == dig(normalize_weather(source))
    assert receipt["after_digest"] != receipt["before_digest"]
    assert receipt["preview"]["status"] == "solved"
    assert any(action["kind"] == "wait" for action in receipt["preview"]["actions"])
    assert verify_session(receipt["preview"]["terminal_session"]) == (
        receipt["preview"]["terminal_session"]
    )
    assert verify_edit(source, json.loads(json.dumps(receipt))) == receipt


def test_gate_edit_and_removal_are_atomic_and_playable():
    source, _ = original_weather_demo()
    digest = dig(normalize_weather(source))
    edited = edit_weather(source, [{
        "kind": "remove-gate", "scene_id": "quay", "exit_id": "north",
    }], digest)
    assert edited["source"]["blocked_exits"] == []
    assert edited["preview"]["status"] == "solved"
    restored = edit_weather(edited["source"], [{
        "kind": "set-gate", "scene_id": "quay", "exit_id": "north",
        "conditions": ["storm"],
    }], edited["after_digest"])
    assert restored["after_digest"] == digest
    assert restored["preview"]["status"] == "solved"


def test_preview_budget_is_explicitly_inconclusive():
    source, _ = original_weather_demo()
    result = edit_weather(source, [{
        "kind": "set-cycle", "conditions": ["storm", "storm", "clear"],
    }], dig(normalize_weather(source)), max_depth=0)
    assert result["preview"]["status"] == "inconclusive"
    assert result["preview"]["terminal_session"] is None


@pytest.mark.parametrize("operations", [
    [], [None], [{"kind": "set-cycle", "conditions": ["storm", "clear", "clear"]}],
    [{"kind": "set-cycle", "conditions": ["sunshine"]}],
    [{"kind": "remove-gate", "scene_id": "quay", "exit_id": "missing"}],
    [{"kind": "set-gate", "scene_id": "quay", "exit_id": "missing",
      "conditions": ["storm"]}],
    [{"kind": "set-gate", "scene_id": "quay", "exit_id": "north",
      "conditions": ["fog"]}],
    [{"kind": "set-cycle", "conditions": ["clear"]}],
])
def test_invalid_or_noop_edits_fail_closed_without_mutating_source(operations):
    source, _ = original_weather_demo()
    before = copy.deepcopy(source)
    with pytest.raises(SceneTravelError):
        edit_weather(source, operations, dig(normalize_weather(source)))
    assert source == before


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(receipt="0" * 64),
    lambda x: x.update(after_digest="0" * 64),
    lambda x: x["preview"].update(status="solved"),
    lambda x: x["preview"]["terminal_session"]["state"].update(weather="fog"),
    lambda x: x["source"]["cycle"].append("fog"),
])
def test_tampered_receipts_fail_closed(mutate):
    source, _ = original_weather_demo()
    report = original_authoring_demo()
    bad = copy.deepcopy(report)
    mutate(bad)
    with pytest.raises(SceneTravelError):
        verify_edit(source, bad)


def test_stale_source_lease_fails_closed():
    source, _ = original_weather_demo()
    with pytest.raises(SceneTravelError, match="stale"):
        edit_weather(source, [{
            "kind": "set-cycle", "conditions": ["storm", "storm", "clear"],
        }], "0" * 64)


def test_installed_cli_authoring_and_verify(capsys):
    source, _ = original_weather_demo()
    assert main(["scene-weather-author", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["preview"]["status"] == "solved"
    assert main([
        "scene-weather-author", "verify",
        "--source-json", json.dumps(source),
        "--receipt-json", json.dumps(receipt),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == receipt


def test_installed_cli_invalid_json_fails_closed(capsys):
    assert main([
        "scene-weather-author", "edit",
        "--source-json", '{"a":1,"a":2}',
        "--operations-json", "[]",
        "--expected-digest", "0" * 64,
    ]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
