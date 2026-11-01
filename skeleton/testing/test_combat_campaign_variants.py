"""Campaign variants: original source -> edits -> play -> save -> export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_campaign import (
    finish_campaign, normalize_campaign, original_campaign,
)
from skeleton.game.gameplay.combat_campaign_package import verify_package
from skeleton.game.gameplay.combat_campaign_variants import (
    compare_campaigns, original_variants_demo, verify_comparison,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _reward(value):
    return [{"kind": "set-reward", "encounter_id": "reed_watch", "value": value}]


def test_replay_proven_variant_selection_preserves_original_source():
    source = original_campaign()
    before = copy.deepcopy(source)
    report = compare_campaigns(source, [_reward(11), _reward(12)],
                               dig(normalize_campaign(source)))
    assert source == before
    assert report["selected_index"] == 2
    assert report["alternatives"][0]["earned_currency"] == 30
    assert report["alternatives"][2]["earned_currency"] == 32
    assert report["selected_package"]["manifest"]["currency"] == 32
    assert report["selected_package"]["manifest"]["phase"] == "won"
    assert verify_package(report["selected_package"]) == report["selected_package"]
    assert verify_comparison(json.loads(json.dumps(report))) == report


def test_unedited_baseline_is_safe_fallback_when_edits_hurt_rewards():
    source = original_campaign()
    result = compare_campaigns(source, [_reward(0)],
                               dig(normalize_campaign(source)))
    assert result["selected_index"] == 0
    assert result["selected_package"]["snapshot"] == finish_campaign(source)


def test_ties_resolve_to_first_source_order_without_unearned_rewards():
    source = original_campaign()
    # Change the turn budget but keep the canonical result unchanged.
    source["encounters"][0]["scenario"]["turn_limit"] = 20
    result = compare_campaigns(source, [[{
        "kind": "set-turn-limit", "encounter_id": "reed_watch", "value": 21,
    }]], dig(normalize_campaign(source)))
    assert result["selected_index"] == 0


@pytest.mark.parametrize("bad", [
    [], [None], [123], [[{"kind": "set-reward",
                          "encounter_id": "reed_watch", "value": True}]],
    [_reward(11)] * 2, [_reward(11)] * 5,
])
def test_invalid_or_duplicate_variants_fail_closed(bad):
    source = original_campaign()
    with pytest.raises(CombatSessionError):
        compare_campaigns(source, bad, dig(normalize_campaign(source)))


def test_stale_digest_rejected_without_editing_source():
    source = original_campaign()
    original = copy.deepcopy(source)
    with pytest.raises(CombatSessionError, match="stale"):
        compare_campaigns(source, [_reward(11)], "0" * 64)
    assert source == original


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(selected_index=0),
    lambda x: x["selected_package"]["manifest"].update(currency=999),
    lambda x: x["alternatives"][1].update(earned_currency=999),
    lambda x: x.update(receipt="0" * 64),
    lambda x: x["source"]["encounters"][0].update(reward=999),
])
def test_tampered_comparison_receipts_fail_closed(mutate):
    report = original_variants_demo()
    bad = copy.deepcopy(report)
    mutate(bad)
    with pytest.raises(CombatSessionError):
        verify_comparison(bad)


def test_installed_cli_demo_verify_and_bad_json(capsys):
    assert main(["combat-campaign-variants", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["selected_index"] == 2
    assert main([
        "combat-campaign-variants", "verify",
        "--report-json", json.dumps(report),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert main([
        "combat-campaign-variants", "compare",
        "--source-json", '{"x":1,"x":2}',
        "--alternatives-json", "[]",
        "--expected-digest", "0" * 64,
    ]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_installed_cli_source_to_portable_save_and_replay(capsys):
    source = original_campaign()
    assert main([
        "combat-campaign-variants", "compare",
        "--source-json", json.dumps(source),
        "--alternatives-json", json.dumps([_reward(11)]),
        "--expected-digest", dig(normalize_campaign(source)),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["selected_index"] == 1
    assert main([
        "combat-campaign-package", "verify",
        "--package-json", json.dumps(report["selected_package"]),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == report["selected_package"]
