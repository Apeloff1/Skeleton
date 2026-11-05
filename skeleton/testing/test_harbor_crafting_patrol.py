"""Source -> patrol -> canonical movement -> save/replay regression."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, demo_actions, digest
from skeleton.game.gameplay.harbor_crafting_patrol import (
    build_patrol, resume_patrol, validate_patrol_board, verify_patrol,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def inputs():
    return (
        json.loads((FIXTURES / "harbor_lantern_quay.json").read_text()),
        json.loads((FIXTURES / "harbor_lantern_quay_patrol.json").read_text()),
    )


def actions():
    core = demo_actions()
    return (core[:3] + [{"op": "collect", "objective": "tide_registry"}]
            + core[3:-2] + [{"op": "collect", "objective": "dock_manifest"}]
            + [{"op": "deliver"}, {"op": "extract"}])


def test_source_to_earned_extraction_and_replay():
    source, board = inputs()
    report = build_patrol(source, board, actions(), require_complete=True)
    status = verify_patrol(report, require_complete=True)
    assert status["complete"] is True
    assert status["score"] == 18
    assert status["collected"] == ["tide_registry", "dock_manifest"]
    assert report["bundle"]["state"]["ending"] == "beacon"
    assert report == build_patrol(source, board, actions(), require_complete=True)


def test_resume_cas_and_terminal_rejection():
    source, board = inputs()
    prefix = build_patrol(source, board, actions()[:5])
    full = resume_patrol(prefix, actions()[5:],
                         expected_digest=prefix["report_digest"], require_complete=True)
    assert verify_patrol(full)["complete"]
    with pytest.raises(HarborError, match="stale"):
        resume_patrol(prefix, [], expected_digest="0" * 64)
    with pytest.raises(HarborError, match="terminal"):
        resume_patrol(full, [], expected_digest=full["report_digest"])


@pytest.mark.parametrize("mutation", [
    lambda b: b["guards"][0].update(sight=99),
    lambda b: b["guards"][0].update(route=[[0, 0]]),
    lambda b: b["guards"][0].update(route=[[1, 1]]),
    lambda b: b["objectives"][0].update(at=[0, 0]),
    lambda b: b["objectives"][1].update(id="tide_registry"),
    lambda b: b.update(exit=[1, 1]),
    lambda b: b.update(alert_limit=True),
    lambda b: b.update(smoke_item="unearned"),
])
def test_hostile_board_rejected(mutation):
    source, board = inputs()
    mutation(board)
    with pytest.raises(HarborError):
        validate_patrol_board(board, source)


@pytest.mark.parametrize("action", [
    {"op": "choose", "choice": "signal"},
    {"op": "extract"},
    {"op": "collect", "objective": "unknown"},
    {"op": "collect", "objective": "dock_manifest"},
    {"op": "smoke"},
    {"op": "collect", "objective": "tide_registry", "admin": True},
])
def test_unearned_actions_rejected(action):
    source, board = inputs()
    with pytest.raises(HarborError):
        build_patrol(source, board, [action])


def test_recomputed_outer_digest_does_not_bypass_replay():
    source, board = inputs()
    report = build_patrol(source, board, actions())
    for mutate in (
        lambda r: r["state"].update(score=9999),
        lambda r: r["events"][0].update(previous="0" * 64),
        lambda r: r["actions"][0].update(direction="west"),
        lambda r: r["board"]["objectives"][0].update(reward=100),
    ):
        altered = deepcopy(report)
        mutate(altered)
        altered["report_digest"] = digest({k: v for k, v in altered.items()
                                            if k != "report_digest"})
        with pytest.raises(HarborError):
            verify_patrol(altered)


def test_guard_detection_and_fail_closed_alert():
    source, board = inputs()
    board["guards"][0]["route"] = [[2, 1]]
    board["guards"][0]["sight"] = 1
    board["alert_limit"] = 2
    with pytest.raises(HarborError, match="terminal"):
        build_patrol(source, board, [{"op": "wait"}] * 3)


def test_hide_does_not_clear_alert_while_spotted():
    source, board = inputs()
    board["guards"][0]["route"] = [[2, 1]]
    board["guards"][0]["sight"] = 1
    report = build_patrol(source, board, [{"op": "hide"}])
    assert report["state"]["alert"] == 1
