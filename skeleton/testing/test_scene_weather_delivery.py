"""Weather deliveries: authored route -> collision -> reward -> replay -> export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather_delivery import (
    advance_deliveries, delivery_summary, new_deliveries,
    normalize_deliveries, original_deliveries, package_deliveries,
    resume_deliveries, verify_deliveries, verify_delivery_package,
)


def test_original_delivery_route_earns_only_canonical_arrival_rewards():
    source, actions = original_deliveries()
    before = copy.deepcopy(source)
    started = new_deliveries(source)
    first = advance_deliveries(started, actions[0])
    assert first["state"]["earned"] == 0
    assert delivery_summary(first)["deliveries"][0]["status"] == "pending"
    finished = resume_deliveries(first, actions[1:])
    assert finished["state"]["phase"] == "won"
    assert finished["state"]["earned"] == 30
    assert [x["status"] for x in delivery_summary(finished)["deliveries"]] == [
        "delivered", "delivered",
    ]
    assert source == before
    assert verify_deliveries(json.loads(json.dumps(finished))) == finished
    portable = package_deliveries(finished)
    assert verify_delivery_package(json.loads(json.dumps(portable))) == portable


def test_weather_blocked_exit_cannot_forge_delivery():
    source, _ = original_deliveries()
    started = new_deliveries(source)
    with pytest.raises(SceneTravelError):
        advance_deliveries(started, {
            "kind": "scene", "action": {"kind": "travel", "exit_id": "north"},
        })
    assert started["state"]["earned"] == 0


def test_deadline_expiry_is_irreversible():
    source, _ = original_deliveries()
    source["deliveries"][0]["deadline"] = 1
    started = new_deliveries(source)
    wait = {"kind": "wait"}
    later = resume_deliveries(started, [wait, wait])
    assert later["state"]["earned"] == 0
    assert delivery_summary(later)["deliveries"][0]["status"] == "expired"


@pytest.mark.parametrize("edit", [
    lambda s: s["deliveries"][1].update(delivery_id="gate_supply"),
    lambda s: s["deliveries"][1].update(destination_scene="missing"),
    lambda s: s["deliveries"][1].update(required_item="invented"),
    lambda s: s["deliveries"][1].update(deadline=True),
    lambda s: s["deliveries"][1].update(reward=10001),
    lambda s: s["deliveries"][0].update(requires=["lantern_supply"]),
    lambda s: s["deliveries"][1].update(requires=["gate_supply", "gate_supply"]),
    lambda s: s["deliveries"][1].update(extra="bad"),
    lambda s: s.update(deliveries=[]),
    lambda s: s.update(schema_version="wrong"),
])
def test_invalid_source_contracts_fail_closed(edit):
    source, _ = original_deliveries()
    edit(source)
    with pytest.raises(SceneTravelError):
        normalize_deliveries(source)


@pytest.mark.parametrize("edit", [
    lambda s: s["state"].update(earned=999),
    lambda s: s["state"]["journal"][0].update(earned_after=999),
    lambda s: s["state"]["journal"][0].update(weather_state_digest="0" * 64),
    lambda s: s["weather_session"]["state"].update(weather="storm"),
    lambda s: s["save"].update(parent_digest="0" * 64),
    lambda s: s.update(source_digest="0" * 64),
])
def test_tampered_nested_weather_save_and_rewards_fail_closed(edit):
    source, actions = original_deliveries()
    checkpoint = advance_deliveries(new_deliveries(source), actions[0])
    changed = copy.deepcopy(checkpoint)
    edit(changed)
    with pytest.raises(SceneTravelError):
        verify_deliveries(changed)


def test_portable_manifest_cannot_claim_unearned_currency():
    source, actions = original_deliveries()
    checkpoint = resume_deliveries(new_deliveries(source), actions)
    package = package_deliveries(checkpoint)
    tampered = copy.deepcopy(package)
    tampered["manifest"]["earned"] = 9999
    with pytest.raises(SceneTravelError):
        verify_delivery_package(tampered)


def test_cannot_resume_terminal_or_exceed_world_budget():
    source, actions = original_deliveries()
    finished = resume_deliveries(new_deliveries(source), actions)
    with pytest.raises(SceneTravelError, match="terminal"):
        advance_deliveries(finished, {"kind": "wait"})
    with pytest.raises(SceneTravelError, match="budget"):
        resume_deliveries(new_deliveries(source), [{"kind": "wait"}] * 513)


def test_cli_playable_route_checkpoint_export_import(capsys):
    source, actions = original_deliveries()
    assert main(["weather-deliveries", "start", "--source-json", json.dumps(source)]) == 0
    started = json.loads(capsys.readouterr().out)
    assert main(["weather-deliveries", "resume", "--session-json", json.dumps(started),
                 "--actions-json", json.dumps(actions)]) == 0
    finished = json.loads(capsys.readouterr().out)
    assert finished["state"]["earned"] == 30
    assert main(["weather-deliveries", "pack", "--session-json", json.dumps(finished)]) == 0
    portable = json.loads(capsys.readouterr().out)
    assert main(["weather-deliveries", "unpack",
                 "--package-json", json.dumps(portable)]) == 0
    assert json.loads(capsys.readouterr().out) == portable
    assert main(["weather-deliveries", "summary",
                 "--session-json", json.dumps(finished)]) == 0
    assert json.loads(capsys.readouterr().out)["earned"] == 30


def test_cli_duplicate_json_and_bad_source_fail_closed(capsys):
    assert main(["weather-deliveries", "start", "--source-json", '{"a":1,"a":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
