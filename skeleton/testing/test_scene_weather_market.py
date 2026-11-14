"""Market settlement: playable caravan -> canonical rewards -> net -> replay."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather_delivery import verify_deliveries
from skeleton.game.gameplay.scene_weather_market import (
    advance_market, market_summary, new_market, normalize_market,
    original_market, package_market, resume_market, verify_market,
    verify_market_package,
)


def _finished():
    source, actions = original_market()
    return resume_market(new_market(source), actions)


def test_original_trade_settles_only_replayed_delivery_rewards():
    session = _finished()
    assert session["state"]["phase"] == "won"
    assert session["state"]["gross"] == 30
    assert session["state"]["fees"] == 2
    assert session["state"]["net"] == 28
    assert session["state"]["reputation"] <= 5
    assert verify_deliveries(session["delivery_session"]) == session["delivery_session"]
    assert session["state"]["gross"] == session["delivery_session"]["state"]["earned"]
    assert verify_market(json.loads(json.dumps(session))) == session
    assert market_summary(session)["net"] == 28
    assert len(market_summary(session)["contracts"]) == 2


def test_checkpoint_resume_matches_one_pass_and_has_parent_lineage():
    source, actions = original_market()
    initial = new_market(source)
    first = advance_market(initial, actions[0])
    assert first["state"]["gross"] == 0
    assert first["save"]["parent_digest"] == dig(initial["save"])
    terminal = resume_market(first, actions[1:])
    assert terminal == resume_market(initial, actions)
    assert initial == new_market(source)


def test_expiry_never_mints_reward_or_reputation():
    source, _ = original_market()
    source["deliveries"]["deliveries"][0]["deadline"] = 1
    started = new_market(source)
    later = resume_market(started, [{"kind": "wait"}, {"kind": "wait"}])
    assert later["state"]["gross"] == 0
    assert later["state"]["net"] == 0
    assert later["state"]["reputation"] == 0
    assert any(entry["status"] == "expired"
               for step in later["state"]["journal"]
               for entry in step["settlements"])


@pytest.mark.parametrize("edit", [
    lambda x: x["contracts"][0].update(commission_bps=-1),
    lambda x: x["contracts"][0].update(commission_bps=5001),
    lambda x: x["contracts"][0].update(commission_bps=True),
    lambda x: x["contracts"][0].update(early_by_ticks=0),
    lambda x: x["contracts"][0].update(early_reputation=101),
    lambda x: x["contracts"][1].update(delivery_id="gate_supply"),
    lambda x: x["contracts"][1].update(delivery_id="unknown"),
    lambda x: x["contracts"][0].update(extra="bad"),
    lambda x: x.update(contracts=[]),
    lambda x: x.update(schema_version="wrong"),
])
def test_invalid_market_source_rejected(edit):
    source, _ = original_market()
    edit(source)
    with pytest.raises(SceneTravelError):
        normalize_market(source)


@pytest.mark.parametrize("edit", [
    lambda x: x["state"].update(gross=9999),
    lambda x: x["state"].update(net=9999),
    lambda x: x["state"].update(reputation=9999),
    lambda x: x["state"]["journal"][-1].update(fees_after=0),
    lambda x: x["state"]["journal"][-1]["settlements"][0].update(net=999),
    lambda x: x["delivery_session"]["state"].update(earned=999),
    lambda x: x["save"].update(parent_digest="bad"),
])
def test_forged_market_rewards_fees_or_nested_save_rejected(edit):
    session = _finished()
    forged = copy.deepcopy(session)
    edit(forged)
    with pytest.raises(SceneTravelError):
        verify_market(forged)


def test_rehashed_package_forgery_still_fails_replay():
    portable = package_market(_finished())
    assert verify_market_package(json.loads(json.dumps(portable))) == portable
    forged = copy.deepcopy(portable)
    forged["manifest"]["net"] = 100000
    forged["receipt"] = dig({k: v for k, v in forged.items() if k != "receipt"})
    with pytest.raises(SceneTravelError):
        verify_market_package(forged)


def test_terminal_and_invalid_action_batch_fail_closed():
    session = _finished()
    with pytest.raises(SceneTravelError, match="terminal"):
        advance_market(session, {"kind": "wait"})
    source, _ = original_market()
    with pytest.raises(SceneTravelError, match="budget"):
        resume_market(new_market(source), [{"kind": "wait"}] * 65)


def _run(capsys, *args):
    status = main(list(args))
    out = capsys.readouterr()
    return status, json.loads(out.out or out.err)


def test_main_cli_playable_market_save_resume_summary_export_import(capsys):
    source, actions = original_market()
    status, started = _run(capsys, "weather-market", "start",
                           "--source-json", json.dumps(source))
    assert status == 0
    status, finished = _run(capsys, "weather-market", "resume",
                            "--session-json", json.dumps(started),
                            "--actions-json", json.dumps(actions))
    assert status == 0 and finished["state"]["net"] == 28
    status, summary = _run(capsys, "weather-market", "summary",
                           "--session-json", json.dumps(finished))
    assert status == 0 and summary["net"] == 28
    status, portable = _run(capsys, "weather-market", "pack",
                            "--session-json", json.dumps(finished))
    assert status == 0 and portable["manifest"]["net"] == 28
    status, restored = _run(capsys, "weather-market", "unpack",
                            "--package-json", json.dumps(portable))
    assert status == 0 and restored == portable


def test_cli_rejects_invalid_json_without_payout(capsys):
    status, error = _run(capsys, "weather-market", "start",
                         "--source-json", '{"a":1,"a":2}')
    assert status == 2 and error["ok"] is False
