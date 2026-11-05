"""Offline market distribution source, replay and tamper acceptance."""
from __future__ import annotations

from copy import deepcopy
import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, decode, demo_actions, digest, load_source
from skeleton.game.gameplay.harbor_crafting_cli import DEFAULT_MISSIONS, DEFAULT_WORLD
from skeleton.game.gameplay.harbor_crafting_market_distribution import (
    build_market_distribution, play_market_distribution,
    verify_market_distribution, verify_market_distribution_play,
)


@pytest.fixture
def distribution():
    return build_market_distribution(
        load_source(DEFAULT_WORLD), decode(DEFAULT_MISSIONS.read_bytes()))


def test_distribution_contains_replay_earned_game_and_economy(distribution):
    summary = verify_market_distribution(distribution)
    assert summary["id"] == "lantern-quay"
    assert summary["demo_ending"] == "beacon"
    assert [x["path"] for x in distribution["manifest"]] == [
        "game-package.json", "market-demo.json",
    ]
    assert distribution["market_demo"]["totals"]["delivered"] is True


def test_packaged_game_accepts_real_player_actions(distribution):
    session = play_market_distribution(distribution, demo_actions(), require_all=False)
    totals = verify_market_distribution_play(session)
    assert totals["ending"] == "beacon"
    assert totals["delivered"] is True


def test_distribution_rejects_rehashed_forged_economy(distribution):
    forged = deepcopy(distribution)
    forged["market_demo"]["totals"]["coin_end"] = 900
    forged["market_demo"]["report_digest"] = digest({
        k: v for k, v in forged["market_demo"].items() if k != "report_digest"
    })
    forged["market_digest"] = forged["market_demo"]["report_digest"]
    forged["manifest"][1]["sha256"] = digest(forged["market_demo"])
    forged["manifest"][1]["bytes"] = len(__import__("skeleton.game.gameplay.harbor_crafting", fromlist=["canonical"]).canonical(forged["market_demo"]))
    forged["distribution_digest"] = digest({
        k: v for k, v in forged.items() if k != "distribution_digest"
    })
    with pytest.raises(HarborError):
        verify_market_distribution(forged)


def test_distribution_play_rejects_forged_reward(distribution):
    session = play_market_distribution(distribution, demo_actions())
    session["totals"]["coin_end"] = 900
    session["play_digest"] = digest({k: v for k, v in session.items() if k != "play_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_market_distribution_play(session)


def test_distribution_rejects_unknown_fields(distribution):
    distribution["script"] = "exec"
    with pytest.raises(HarborError):
        verify_market_distribution(distribution)
