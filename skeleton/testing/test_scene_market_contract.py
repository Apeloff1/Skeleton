"""Timed market contracts: original gameplay, replay, export and adversarial saves."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_contract import (
    _advance, cli, contract_board, export_contract, import_contract,
    new_contract, normalize_contract_source, original_contract,
    resume_contract, simulate_contract, verify_contract,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_complete_original_market_contract_campaign():
    source, actions = original_contract()
    final = simulate_contract(source, actions)
    assert final["state"]["phase"] == "won"
    assert final["state"]["score"] == 25
    assert final["state"]["completed"] == ["sanctuary_commission"]
    assert final["state"]["market"]["state"]["reputation"] == 5
    assert final["state"]["market"]["state"]["goods"] == {}
    assert verify_contract(json.loads(json.dumps(final))) == final
    assert import_contract(json.loads(json.dumps(export_contract(final)))) == final
    board = contract_board(final)
    assert board["contracts"][0]["completed"] is True
    assert board["score"] == 25
    assert board["checksum"] == dig({k: v for k, v in board.items() if k != "checksum"})


@pytest.mark.parametrize("split", [0, 1, 2, 5, 6, 8, 10])
def test_contract_resume_exact_replay(split):
    source, actions = original_contract()
    partial = simulate_contract(source, actions[:split])
    final = resume_contract(json.loads(json.dumps(partial)), actions[split:])
    assert final == simulate_contract(source, actions)


def test_score_never_mints_goods_or_credits():
    source, actions = original_contract()
    before = simulate_contract(source, actions[:9])
    assert before["state"]["score"] == 0
    final = simulate_contract(source, actions)
    assert final["state"]["market"]["state"]["credits"] == 1
    assert final["state"]["market"]["state"]["goods"] == {}
    assert final["state"]["score"] == 25
    with pytest.raises(SceneTravelError):
        _advance(final, {"kind": "buy", "offer_id": "copper_badge"})


def test_required_deadline_missed_fails_closed():
    source, actions = original_contract()
    source["contracts"][0]["deadline_tick"] = 1
    lost = simulate_contract(source, actions[:2])
    assert lost["state"]["phase"] == "lost"
    assert lost["state"]["score"] == 0
    with pytest.raises(SceneTravelError, match="terminal"):
        resume_contract(lost, actions[2:])


def test_optional_contract_cannot_override_underlying_game_result():
    source, actions = original_contract()
    source["required_contracts"] = ["sanctuary_commission"]
    skipped = [action for action in actions if action.get("kind") != "deliver"]
    final = simulate_contract(source, skipped)
    assert final["state"]["phase"] == "lost"
    assert final["state"]["score"] == 0


@pytest.mark.parametrize("change", [
    lambda s: s["contracts"][0].update(delivery_id="fabricated"),
    lambda s: s["contracts"][0].update(reward_score=True),
    lambda s: s["contracts"][0].update(deadline_tick=0),
    lambda s: s["contracts"][0].update(min_reputation=-1),
    lambda s: s["contracts"].append(copy.deepcopy(s["contracts"][0])),
    lambda s: s.update(required_contracts=["nonexistent"]),
    lambda s: s.update(schema_version="future"),
])
def test_invalid_authored_contracts_rejected(change):
    source, _ = original_contract()
    change(source)
    with pytest.raises(SceneTravelError):
        normalize_contract_source(source)


@pytest.mark.parametrize("change", [
    lambda s: s["state"].update(score=999),
    lambda s: s["state"].update(completed=["sanctuary_commission", "forged"]),
    lambda s: s["state"]["market"]["state"].update(credits=999),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["journal"][0]["action"].update(kind="deliver"),
    lambda s: s["save"].update(tick=0),
    lambda s: s.update(source_digest="0" * 64),
])
def test_forged_contract_saves_rejected(change):
    source, actions = original_contract()
    altered = copy.deepcopy(simulate_contract(source, actions))
    change(altered)
    with pytest.raises(SceneTravelError):
        verify_contract(altered)


def test_portable_contract_bundle_detects_tampering():
    source, actions = original_contract()
    bundle = export_contract(simulate_contract(source, actions))
    for key in ("checksum", "source_digest", "state_digest"):
        forged = copy.deepcopy(bundle)
        forged[key] = "0" * 64
        with pytest.raises(SceneTravelError):
            import_contract(forged)


def test_rejected_batch_does_not_mutate_checkpoint():
    source, actions = original_contract()
    checkpoint = simulate_contract(source, actions[:5])
    snapshot = copy.deepcopy(checkpoint)
    with pytest.raises(SceneTravelError):
        resume_contract(checkpoint, [
            {"kind": "buy", "offer_id": "copper_badge"},
            {"kind": "buy", "offer_id": "copper_badge"},
        ])
    assert checkpoint == snapshot


def test_cli_is_user_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-contract", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["phase"] == "won"
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"x":1,"x":2}',
                "--actions-json", "[]"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
