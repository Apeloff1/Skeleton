"""End-to-end canonical trading, earned goods and replay acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_market import (
    _advance, cli, export_market, import_market, new_market,
    normalize_market, original_market, resume_market, simulate_market,
    verify_market,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_market_original_complete_delivery_and_export():
    source, actions = original_market()
    saved = simulate_market(source, actions)
    assert saved["state"]["phase"] == "won"
    assert saved["state"]["credits"] == 1
    assert saved["state"]["goods"] == {}
    assert saved["state"]["purchases"] == {"copper_badge": 1}
    assert saved["state"]["crafted"] == {"seal_press": 1}
    assert saved["state"]["delivered"] == ["sanctuary_seal"]
    assert saved["state"]["reputation"] == 5
    assert verify_market(json.loads(json.dumps(saved))) == saved
    assert import_market(json.loads(json.dumps(export_market(saved)))) == saved


@pytest.mark.parametrize("split", [0, 1, 2, 5, 6, 7, 8, 9, 10, 11])
def test_market_replay_split_and_resume(split):
    source, actions = original_market()
    partial = simulate_market(source, actions[:split])
    assert resume_market(json.loads(json.dumps(partial)), actions[split:]) == (
        simulate_market(source, actions)
    )


def test_no_unearned_money_or_free_goods():
    source, actions = original_market()
    start = new_market(source)
    with pytest.raises(SceneTravelError, match="position"):
        _advance(start, {"kind": "buy", "offer_id": "copper_badge"})
    gate = simulate_market(source, actions[:5])
    assert gate["state"]["credits"] == 3
    bought = _advance(gate, {"kind": "buy", "offer_id": "copper_badge"})
    assert bought["state"]["credits"] == 1
    with pytest.raises(SceneTravelError, match="stock"):
        _advance(bought, {"kind": "buy", "offer_id": "copper_badge"})
    assert bought["state"]["purchases"] == {"copper_badge": 1}


def test_craft_and_delivery_require_position_and_earned_inventory():
    source, actions = original_market()
    gate = simulate_market(source, actions[:5])
    with pytest.raises(SceneTravelError, match="station position"):
        _advance(gate, {"kind": "craft", "recipe_id": "seal_press"})
    with pytest.raises(SceneTravelError, match="recipient position"):
        _advance(gate, {"kind": "deliver", "delivery_id": "sanctuary_seal"})
    moved = simulate_market(source, actions[:7])
    recipient = _advance(moved, {"kind": "tile", "action": {"kind": "move", "direction": "east"}})
    with pytest.raises(SceneTravelError, match="earned goods"):
        _advance(recipient, {"kind": "deliver", "delivery_id": "sanctuary_seal"})
    crafted = _advance(moved, {"kind": "craft", "recipe_id": "seal_press"})
    with pytest.raises(SceneTravelError, match="earned goods"):
        _advance(crafted, {"kind": "craft", "recipe_id": "seal_press"})


def test_undelivered_objective_denies_ending():
    source, actions = original_market()
    skipped = [a for a in actions if a.get("kind") != "deliver"]
    result = simulate_market(source, skipped)
    assert result["state"]["tile"]["state"]["phase"] == "won"
    assert result["state"]["phase"] == "lost"
    assert result["state"]["reputation"] == 0


@pytest.mark.parametrize("mutate", [
    lambda s: s["coin_pickups"][0].update(pickup="quay:unearned"),
    lambda s: s["coin_pickups"][0].update(amount=True),
    lambda s: s["markets"][0]["offers"][0].update(stock=0),
    lambda s: s["markets"][0]["offers"][0].update(price=-1),
    lambda s: s["markets"][0].update(at=[9, 9]),
    lambda s: s["recipes"][0].update(inputs={"badge": 0}),
    lambda s: s["deliveries"][0].update(reputation=101),
    lambda s: s.update(required_deliveries=["forged"]),
    lambda s: s.update(schema_version="future"),
])
def test_bad_authored_economy_rejected(mutate):
    source, _ = original_market()
    mutate(source)
    with pytest.raises(SceneTravelError):
        normalize_market(source)


@pytest.mark.parametrize("mutate", [
    lambda s: s["state"].update(credits=1000),
    lambda s: s["state"].update(goods={"seal": 10}),
    lambda s: s["state"].update(reputation=1000),
    lambda s: s["state"].update(delivered=["sanctuary_seal", "extra"]),
    lambda s: s["journal"][0]["action"].update(kind="buy"),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s.update(source_digest="0" * 64),
    lambda s: s["save"].update(tick=0),
])
def test_market_forged_saves_rejected(mutate):
    source, actions = original_market()
    bad = copy.deepcopy(simulate_market(source, actions))
    mutate(bad)
    with pytest.raises(SceneTravelError):
        verify_market(bad)


def test_bundle_tamper_and_source_rebind_fail():
    source, actions = original_market()
    bundle = export_market(simulate_market(source, actions))
    for key in ("checksum", "source_digest", "state_digest"):
        bad = copy.deepcopy(bundle)
        bad[key] = "0" * 64
        with pytest.raises(SceneTravelError):
            import_market(bad)


def test_market_cli_user_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["phase"] == "won"
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"x":1,"x":2}',
                "--actions-json", "[]"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_transactional_rejection_leaves_checkpoint_unchanged():
    source, actions = original_market()
    checkpoint = simulate_market(source, actions[:5])
    before = copy.deepcopy(checkpoint)
    with pytest.raises(SceneTravelError):
        resume_market(checkpoint, [
            {"kind": "buy", "offer_id": "copper_badge"},
            {"kind": "buy", "offer_id": "copper_badge"},
        ])
    assert checkpoint == before
