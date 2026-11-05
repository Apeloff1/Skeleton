"""Replay-verified economic and saved-futures acceptance."""
from __future__ import annotations

from copy import deepcopy
import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, demo_actions, digest, export_bundle, load_source
from skeleton.game.gameplay.harbor_crafting_cli import DEFAULT_WORLD
from skeleton.game.gameplay.harbor_crafting_market import (
    market_checkpoint, market_futures, market_report, market_resume,
    verify_market_futures, verify_market_report,
)
from skeleton.game.gameplay.harbor_crafting_sessions import branch_portfolio


@pytest.fixture
def victory():
    source = load_source(DEFAULT_WORLD)
    return export_bundle(source, demo_actions(), require_win=True)


def test_earned_economy_and_victory(victory):
    report = market_report(victory)
    totals = verify_market_report(report)
    assert totals["ending"] == "beacon"
    assert totals["delivered"] is True
    assert totals["coin_end"] + totals["coin_spent"] == totals["coin_start"]
    assert totals["operations"]["gather"] > 0
    assert totals["operations"]["craft"] > 0
    assert totals["operations"]["deliver"] == 1
    assert len(report["entries"]) == len(victory["events"])


def test_checkpoint_cas_and_replay_prefix(victory):
    report = market_report(victory)
    tick = len(victory["events"]) - 1
    partial = market_checkpoint(report, tick)
    assert partial["totals"]["ending"] is None
    continuation = [victory["events"][-1]["action"]]
    assert market_resume(
        partial, continuation, expected_terminal_digest=partial["terminal_digest"],
        require_win=True,
    ) == report
    with pytest.raises(HarborError, match="stale"):
        market_resume(partial, continuation, expected_terminal_digest="0" * 64)
    with pytest.raises(HarborError):
        market_checkpoint(report, tick + 10)


@pytest.mark.parametrize("field,value", [
    ("coin_end", 1000), ("coin_spent", -1), ("ending", "safe_harbor"),
    ("delivered", False),
])
def test_rehashed_forged_totals_rejected(victory, field, value):
    report = market_report(victory)
    report["totals"][field] = value
    report["report_digest"] = digest({k: v for k, v in report.items() if k != "report_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_market_report(report)


def test_rehashed_transition_forgery_rejected(victory):
    report = market_report(victory)
    report["entries"][0]["coin_delta"] = 900
    report["report_digest"] = digest({k: v for k, v in report.items() if k != "report_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_market_report(report)


def test_saved_futures_have_earned_different_endings(victory):
    source = victory["source"]
    actions = demo_actions()
    root = export_bundle(source, actions[:-1])
    portfolio = branch_portfolio(root, {
        "beacon": [actions[-1]],
        "shelter": [{"op": "choose", "choice": "shelter"}],
    })
    report = market_futures(portfolio)
    result = verify_market_futures(report)
    assert [x["totals"]["ending"] for x in result] == ["beacon", "safe_harbor"]
    forged = deepcopy(report)
    forged["entries"][0]["totals"]["coin_end"] = 1000
    forged["report_digest"] = digest({k: v for k, v in forged.items() if k != "report_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_market_futures(forged)


def test_market_report_shapes_fail_closed(victory):
    for invalid in (None, [], {}, {"schema": "skeleton.game.harbor.market-ledger.v1"}):
        with pytest.raises(HarborError):
            verify_market_report(invalid)
