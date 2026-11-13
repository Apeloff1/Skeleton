"""Deterministic original salvage gameplay and hostile replay regression."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, demo_actions, digest
from skeleton.game.gameplay.harbor_crafting_salvage import (
    build_salvage, resume_salvage, validate_salvage_board, verify_salvage,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def inputs():
    source = json.loads((FIXTURES / "harbor_lantern_quay.json").read_text())
    board = json.loads((FIXTURES / "harbor_lantern_quay_salvage.json").read_text())
    return source, board


def actions():
    core = demo_actions()
    return core[:3] + [{"op": "salvage", "site": "wrecked_skiff"}] + core[3:-2] + [
        {"op": "salvage", "site": "tide_cache"}, {"op": "offload"},
        {"op": "deliver"}, {"op": "rescue"},
    ]


def test_source_to_replay_and_earned_rescue():
    source, board = inputs()
    report = build_salvage(source, board, actions(), require_complete=True)
    status = verify_salvage(report, require_complete=True)
    assert status["complete"] is True
    assert status["reward"] == 11
    assert status["secured"] == ["wrecked_skiff", "tide_cache"]
    assert report["bundle"]["state"]["ending"] == "beacon"
    assert report == build_salvage(source, board, actions(), require_complete=True)


def test_cas_resume_and_stale_lease():
    source, board = inputs()
    prefix = build_salvage(source, board, actions()[:5])
    resumed = resume_salvage(prefix, actions()[5:], expected_digest=prefix["report_digest"],
                             require_complete=True)
    assert verify_salvage(resumed)["complete"]
    with pytest.raises(HarborError, match="stale"):
        resume_salvage(prefix, [], expected_digest="0" * 64)


@pytest.mark.parametrize("change", [
    lambda b: b["sites"][0].update(at=[0, 0]),
    lambda b: b["sites"][0].update(weight=99),
    lambda b: b["sites"][1].update(id="wrecked_skiff"),
    lambda b: b.update(tool="nonexistent"),
    lambda b: b.update(hull=True),
    lambda b: b.update(tide_period=0),
    lambda b: b["sites"][0].update(at=[4, 2]),
    lambda b: b.update(cargo_capacity=1),
])
def test_hostile_board_rejected(change):
    source, board = inputs()
    change(board)
    with pytest.raises(HarborError):
        validate_salvage_board(board, source)


@pytest.mark.parametrize("bad_action", [
    {"op": "choose", "choice": "signal"},
    {"op": "salvage", "site": "not_a_site"},
    {"op": "offload"},
    {"op": "patch"},
    {"op": "rescue"},
    {"op": "move", "direction": "diagonal"},
    {"op": "salvage", "site": "wrecked_skiff", "admin": True},
])
def test_unearned_actions_rejected(bad_action):
    source, board = inputs()
    with pytest.raises(HarborError):
        build_salvage(source, board, [bad_action])


def test_replay_tamper_and_recomputed_digest_rejected():
    source, board = inputs()
    report = build_salvage(source, board, actions())
    for change in (
        lambda r: r["state"].update(reward=10000),
        lambda r: r["events"][0].update(previous="0" * 64),
        lambda r: r["actions"][0].update(direction="west"),
        lambda r: r["board"]["sites"][0].update(reward=99),
    ):
        damaged = deepcopy(report)
        change(damaged)
        damaged["report_digest"] = digest({k: v for k, v in damaged.items()
                                            if k != "report_digest"})
        with pytest.raises(HarborError):
            verify_salvage(damaged)


def test_salvage_capacity_and_no_duplicate_claim():
    source, board = inputs()
    with pytest.raises(HarborError, match="already recovered"):
        build_salvage(source, board, actions()[:4] +
                      [{"op": "salvage", "site": "wrecked_skiff"}])
    board["cargo_capacity"] = 2
    with pytest.raises(HarborError, match="capacity"):
        build_salvage(source, board, actions())
