"""Source-fenced NPC rescue editing, preview replay and CLI acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather_rescue import (
    normalize_rescue, original_rescue, verify_rescue,
)
from skeleton.game.gameplay.scene_weather_rescue_author import (
    author_rescue, original_authoring_demo, verify_authoring,
)


def test_original_authoring_changes_only_earned_reward_and_replays():
    source, _ = original_rescue()
    original = copy.deepcopy(source)
    receipt = original_authoring_demo()
    assert source == original
    assert receipt["source"]["npcs"][0]["reward"] == 30
    assert receipt["preview"]["state"]["earned"] == 30
    assert receipt["preview"]["state"]["phase"] == "won"
    assert verify_rescue(receipt["preview"]) == receipt["preview"]
    assert verify_authoring(source, receipt) == receipt


def test_authoring_exposure_changes_actual_outcome_without_forged_reward():
    source, actions = original_rescue()
    receipt = author_rescue(
        source, [{"npc_id": "canal_medic", "field": "max_storm_exposure", "value": 0}],
        dig(normalize_rescue(source)), actions[:3],
    )
    assert receipt["preview"]["state"]["phase"] == "lost"
    assert receipt["preview"]["state"]["earned"] == 0
    assert verify_authoring(source, receipt) == receipt


@pytest.mark.parametrize("edits", [
    [{"npc_id": "canal_medic", "field": "reward", "value": 25}],
    [{"npc_id": "unknown", "field": "reward", "value": 26}],
    [{"npc_id": "canal_medic", "field": "deadline", "value": 0}],
    [{"npc_id": "canal_medic", "field": "shelter_scene", "value": "quay"}],
    [{"npc_id": "canal_medic", "field": "unknown", "value": 1}],
    [{"npc_id": "canal_medic", "field": "reward", "value": 26, "extra": 1}],
])
def test_invalid_edits_fail_without_mutating_source(edits):
    source, actions = original_rescue()
    before = copy.deepcopy(source)
    with pytest.raises(SceneTravelError):
        author_rescue(source, edits, dig(normalize_rescue(source)), actions)
    assert source == before


def test_stale_digest_and_tampered_receipt_fail_closed():
    source, actions = original_rescue()
    edits = [{"npc_id": "canal_medic", "field": "reward", "value": 30}]
    with pytest.raises(SceneTravelError, match="stale"):
        author_rescue(source, edits, "0" * 64, actions)
    receipt = author_rescue(source, edits, dig(normalize_rescue(source)), actions)
    bad = copy.deepcopy(receipt)
    bad["preview"]["state"]["earned"] = 1000
    with pytest.raises(SceneTravelError):
        verify_authoring(source, bad)
    bad = copy.deepcopy(receipt)
    bad["operations"][0]["value"] = 31
    with pytest.raises(SceneTravelError):
        verify_authoring(source, bad)


def test_installed_cli_source_edit_preview_and_verification(capsys):
    assert main(["scene-weather-rescue-author", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    source, _ = original_rescue()
    assert main([
        "scene-weather-rescue-author", "verify",
        "--source-json", json.dumps(source),
        "--receipt-json", json.dumps(receipt),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
