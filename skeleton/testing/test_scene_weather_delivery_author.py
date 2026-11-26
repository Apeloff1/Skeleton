"""Delivery editing: source lease -> compile -> route -> package -> replay."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather_delivery import (
    normalize_deliveries, original_deliveries,
)
from skeleton.game.gameplay.scene_weather_delivery_author import (
    author_deliveries, original_authoring_demo, verify_delivery_authoring,
)


def _digest(source):
    return dig(normalize_deliveries(source))


def test_authoring_uses_real_playable_route_and_portable_reward():
    source, _ = original_deliveries()
    before = copy.deepcopy(source)
    report = author_deliveries(source, [
        {"kind": "set-reward", "delivery_id": "gate_supply", "value": 12},
    ], _digest(source))
    assert source == before
    assert report["before_digest"] != report["after_digest"]
    assert report["preview_route"]["status"] == "solved"
    assert report["preview_route"]["terminal_package"]["manifest"]["earned"] == 32
    assert verify_delivery_authoring(source, json.loads(json.dumps(report))) == report


def test_valid_additional_delivery_compiles_and_replays():
    source, _ = original_deliveries()
    new = {
        "delivery_id": "second_gate", "destination_scene": "gate",
        "required_item": "brass_key", "deadline": 6, "reward": 4,
        "requires": ["gate_supply"],
    }
    report = author_deliveries(source, [
        {"kind": "add-delivery", "delivery": new},
    ], _digest(source))
    assert len(report["source"]["deliveries"]) == 3
    assert report["preview_route"]["status"] == "solved"
    assert report["preview_route"]["terminal_package"]["manifest"]["earned"] == 34


def test_deadline_change_can_produce_explicit_inconclusive_or_unreachable():
    source, _ = original_deliveries()
    report = author_deliveries(source, [
        {"kind": "set-deadline", "delivery_id": "gate_supply", "value": 1},
    ], _digest(source))
    assert report["preview_route"]["status"] in ("unreachable", "inconclusive")
    assert report["preview_route"]["terminal_package"] is None


@pytest.mark.parametrize("operations", [
    [],
    [None],
    [{"kind": "exec", "delivery_id": "gate_supply", "value": 2}],
    [{"kind": "set-reward", "delivery_id": "missing", "value": 2}],
    [{"kind": "set-reward", "delivery_id": "gate_supply", "value": 10}],
    [{"kind": "set-reward", "delivery_id": "gate_supply", "value": True}],
    [{"kind": "set-deadline", "delivery_id": "gate_supply", "value": 0}],
    [{"kind": "set-destination", "delivery_id": "gate_supply", "value": "missing"}],
    [{"kind": "set-item", "delivery_id": "gate_supply", "value": "invented"}],
    [{"kind": "set-requires", "delivery_id": "gate_supply",
      "value": ["lantern_supply"]}],
    [{"kind": "remove-delivery", "delivery_id": "gate_supply"}],
    [{"kind": "add-delivery", "delivery": {"bad": 1}}],
])
def test_bad_edit_rejected_atomically(operations):
    source, _ = original_deliveries()
    before = copy.deepcopy(source)
    with pytest.raises(SceneTravelError):
        author_deliveries(source, operations, _digest(source))
    assert source == before


def test_stale_source_and_tampered_preview_rejected():
    source, _ = original_deliveries()
    with pytest.raises(SceneTravelError, match="stale"):
        author_deliveries(source, [
            {"kind": "set-reward", "delivery_id": "gate_supply", "value": 12},
        ], "0" * 64)
    report = original_authoring_demo()
    for key in ("receipt", "after_digest"):
        tampered = copy.deepcopy(report)
        tampered[key] = "0" * 64
        with pytest.raises(SceneTravelError):
            verify_delivery_authoring(source, tampered)
    tampered = copy.deepcopy(report)
    tampered["preview_route"]["terminal_package"]["manifest"]["earned"] = 999
    with pytest.raises(SceneTravelError):
        verify_delivery_authoring(source, tampered)


def test_cli_edit_verify_and_bad_json(capsys):
    source, _ = original_deliveries()
    assert main(["weather-deliveries-author", "edit",
                 "--source-json", json.dumps(source),
                 "--operations-json", json.dumps([{
                     "kind": "set-reward", "delivery_id": "gate_supply",
                     "value": 12,
                 }]), "--expected-digest", _digest(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert main(["weather-deliveries-author", "verify",
                 "--source-json", json.dumps(source),
                 "--receipt-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert main(["weather-deliveries-author", "edit",
                 "--source-json", '{"x":1,"x":2}',
                 "--operations-json", "[]", "--expected-digest", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
