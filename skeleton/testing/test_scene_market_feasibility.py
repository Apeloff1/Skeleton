"""Conservative market authoring diagnostics never claim proof of play."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import cli, original_market
from skeleton.game.gameplay.scene_market_feasibility import (
    analyze_market_feasibility,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_market_potentially_reachable_but_not_certified():
    source, _ = original_market()
    report = analyze_market_feasibility(source)
    assert report["status"] == "potentially_reachable_unproven"
    assert report["maximum_collectible_credits"] == 3
    assert report["potential_goods"] == ["badge", "seal"]
    assert report["potential_recipes"] == ["seal_press"]
    assert report["unreachable_required_deliveries"] == []
    assert report["method"] == "bounded_overapproximation_not_gameplay_proof"
    assert report["checksum"] == dig({
        k: v for k, v in report.items() if k != "checksum"
    })


def test_unaffordable_offer_breaks_required_delivery_chain():
    source, _ = original_market()
    source["markets"][0]["offers"][0]["price"] = 4
    report = analyze_market_feasibility(source)
    assert report["individually_unaffordable_offers"] == ["copper_badge"]
    assert report["potential_goods"] == []
    assert report["blocked_recipes"] == ["seal_press"]
    assert report["unreachable_required_deliveries"] == ["sanctuary_seal"]
    assert report["status"] == "definitely_unreachable"


def test_unrelated_unaffordable_offer_is_warning_not_campaign_failure():
    source, _ = original_market()
    extra = copy.deepcopy(source["markets"][0]["offers"][0])
    extra.update(offer_id="golden_banner", item_id="banner", price=500)
    source["markets"][0]["offers"].append(extra)
    report = analyze_market_feasibility(source)
    assert report["individually_unaffordable_offers"] == ["golden_banner"]
    assert report["unreachable_required_deliveries"] == []
    assert report["status"] == "potentially_reachable_unproven"


def test_missing_recipe_input_proves_required_delivery_unavailable():
    source, _ = original_market()
    source["recipes"][0]["inputs"] = {"unobtainable_ore": 1}
    report = analyze_market_feasibility(source)
    assert report["blocked_recipes"] == ["seal_press"]
    assert report["unreachable_required_deliveries"] == ["sanctuary_seal"]


def test_optional_delivery_unavailable_does_not_block_required_delivery():
    source, _ = original_market()
    source["deliveries"].append({
        "delivery_id": "optional_banner", "scene_id": "gate", "at": [2, 1],
        "goods": {"banner": 1}, "reputation": 1,
    })
    report = analyze_market_feasibility(source)
    assert report["unavailable_deliveries"] == ["optional_banner"]
    assert report["unreachable_required_deliveries"] == []
    assert report["status"] == "potentially_reachable_unproven"


def test_source_is_not_mutated_and_invalid_authoring_fails_closed():
    source, _ = original_market()
    before = copy.deepcopy(source)
    assert analyze_market_feasibility(source)
    assert source == before
    source["coin_pickups"][0]["amount"] = True
    with pytest.raises(SceneTravelError):
        analyze_market_feasibility(source)


def test_feasibility_cli_user_reachable(capsys):
    from skeleton.__main__ import main
    source, _ = original_market()
    args = ["feasibility", "--source-json", json.dumps(source)]
    assert main(["scene-market", *args]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "potentially_reachable_unproven"
    assert cli(["feasibility", "--source-json", '{"bad":1}']) == 2
    assert "error" in json.loads(capsys.readouterr().err)
