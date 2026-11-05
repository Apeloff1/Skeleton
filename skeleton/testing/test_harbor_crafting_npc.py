"""Canonical NPC patrol observations and bounded WAIT forecasts."""
from __future__ import annotations

from copy import deepcopy
import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, demo_actions, digest, export_bundle, load_source
from skeleton.game.gameplay.harbor_crafting_cli import DEFAULT_WORLD
from skeleton.game.gameplay.harbor_crafting_npc import (
    npc_forecast, npc_observations, verify_npc_forecast, verify_npc_observations,
)


@pytest.fixture
def source():
    return load_source(DEFAULT_WORLD)


def test_npc_observations_replay_real_movement_and_trade(source):
    bundle = export_bundle(source, demo_actions())
    report = npc_observations(bundle)
    assert len(report["entries"]) == len(bundle["events"]) + 1
    assert verify_npc_observations(report)["state_digest"] == bundle["terminal_digest"]
    assert all(entry["npc"] in source["npc"]["route"] for entry in report["entries"])
    assert all(entry["distance"] >= 0 for entry in report["entries"])


def test_npc_forecast_uses_canonical_wait_actions(source):
    bundle = export_bundle(source, [])
    forecast = npc_forecast(bundle, 4)
    assert len(forecast["entries"]) == 4
    assert verify_npc_forecast(forecast)["tick"] == 4
    assert all(entry["player"] == source["start"] for entry in forecast["entries"])
    assert all(action == {"op": "wait"} for action in forecast["actions"])


def test_npc_forecast_rejects_finished_and_exhausted(source):
    finished = export_bundle(source, demo_actions(), require_win=True)
    with pytest.raises(HarborError, match="completed"):
        npc_forecast(finished, 1)
    with pytest.raises(HarborError):
        npc_forecast(export_bundle(source, []), 33)


def test_rehashed_forged_patrol_is_rejected(source):
    report = npc_observations(export_bundle(source, demo_actions()))
    report["entries"][0]["npc"] = [1, 1]
    report["report_digest"] = digest({k: v for k, v in report.items() if k != "report_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_npc_observations(report)


def test_rehashed_forged_forecast_is_rejected(source):
    forecast = npc_forecast(export_bundle(source, []), 3)
    forged = deepcopy(forecast)
    forged["entries"][0]["trade_reachable"] = not forged["entries"][0]["trade_reachable"]
    forged["forecast_digest"] = digest({k: v for k, v in forged.items() if k != "forecast_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_npc_forecast(forged)


def test_trade_reachability_checks_stock_coins_and_capacity(source):
    from skeleton.game.gameplay.harbor_crafting import MAX_INVENTORY, initial_state
    from skeleton.game.gameplay.harbor_crafting_npc import _observe
    state = initial_state(source)
    state["pos"] = [4, 1]  # Adjacent to the initial merchant position.
    assert _observe(state, source)["trade_reachable"] is True
    state["coins"] = 0
    assert _observe(state, source)["trade_reachable"] is False
    state["coins"] = source["npc"]["price"]
    state["npc_stock"] = {"food": 0}
    assert _observe(state, source)["trade_reachable"] is False
    state["npc_stock"] = {"food": 1}
    state["inventory"] = {"wood": MAX_INVENTORY}
    assert _observe(state, source)["trade_reachable"] is False
