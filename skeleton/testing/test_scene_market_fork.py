"""Executable fork previews, source custody and player-commit acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_market import (
    export_market, import_market, original_market, simulate_market, verify_market,
)
from skeleton.game.gameplay.scene_market_fork import (
    MAX_CANDIDATES, choose_market_fork, cli, evaluate_market_fork,
    export_market_fork, import_market_fork, normalize_candidates,
    original_fork, verify_market_fork,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_fork_replays_to_real_market_victory():
    report = original_fork()
    assert verify_market_fork(report) == report
    assert report["heuristic_candidate"] == "complete_delivery"
    assert [x["status"] for x in report["outcomes"]] == ["accepted", "blocked"]
    assert report["outcomes"][1]["blocked_step"] == 0
    selected = choose_market_fork(report, "complete_delivery")
    assert selected["state"]["phase"] == "won"
    assert selected["state"]["reputation"] == 5
    assert selected["state"]["credits"] == 1
    assert import_market(export_market(selected)) == selected


def test_preview_is_transactional_and_branch_replays_independently():
    source, actions = original_market()
    checkpoint = simulate_market(source, actions[:5])
    before = copy.deepcopy(checkpoint)
    plans = [
        {"candidate_id": "buy", "actions": [actions[5]]},
        {"candidate_id": "skip", "actions": [actions[6]]},
    ]
    report = evaluate_market_fork(checkpoint, plans)
    assert checkpoint == before
    assert report["checkpoint"] == before
    assert [x["candidate_id"] for x in report["outcomes"]] == ["buy", "skip"]
    chosen = choose_market_fork(report, "buy")
    assert chosen["state"]["credits"] == checkpoint["state"]["credits"] - 2
    assert checkpoint["state"]["credits"] == 3
    assert verify_market(chosen) == chosen
    assert choose_market_fork(report, "skip") != chosen


def test_blocked_choice_is_never_committed_or_ranked():
    source, _ = original_market()
    checkpoint = simulate_market(source, [])
    report = evaluate_market_fork(checkpoint, [{
        "candidate_id": "illegal", "actions": [
            {"kind": "buy", "offer_id": "copper_badge"},
        ],
    }])
    assert report["heuristic_candidate"] is None
    assert report["outcomes"][0]["state_digest"] is None
    assert report["outcomes"][0]["status"] == "blocked"
    with pytest.raises(SceneTravelError, match="blocked fork"):
        choose_market_fork(report, "illegal")
    assert verify_market(checkpoint) == checkpoint


@pytest.mark.parametrize("mutation", [
    lambda r: r["checkpoint"]["state"].update(credits=900),
    lambda r: r["checkpoint"].update(state_digest="0" * 64),
    lambda r: r["outcomes"][0].update(credits=900),
    lambda r: r["outcomes"][0].update(status="blocked"),
    lambda r: r["outcomes"][1].update(blocked_step=None),
    lambda r: r.update(heuristic_candidate="unearned_purchase"),
    lambda r: r.update(source_digest="0" * 64),
    lambda r: r.update(checkpoint_state_digest="0" * 64),
    lambda r: r.update(qualification="certified_optimal"),
    lambda r: r["candidates"][0]["actions"][0].update(kind="deliver"),
    lambda r: r["candidates"][0].update(candidate_id="forged_candidate"),
])
def test_rejects_forged_branch_witness_even_if_checksum_recomputed(mutation):
    report = copy.deepcopy(original_fork())
    mutation(report)
    report["checksum"] = __import__(
        "skeleton.game.gameplay.flgb_gameplay_runtime", fromlist=["dig"]
    ).dig({k: v for k, v in report.items() if k != "checksum"})
    with pytest.raises((SceneTravelError, KeyError, TypeError)):
        verify_market_fork(report)


@pytest.mark.parametrize("candidates", [
    [],
    [{"candidate_id": "same", "actions": [{"kind": "tile", "action": {}}]}] * 2,
    [{"candidate_id": "empty", "actions": []}],
    [{"candidate_id": "bool", "actions": [True]}],
    [{"candidate_id": "unknown", "actions": [{"kind": "teleport"}]}],
    [{"candidate_id": "extra", "actions": [{"kind": "buy", "offer_id": "x", "bonus": 1}]}],
    [{"candidate_id": "x", "actions": [{"kind": "tile", "action": {}}]}]
    * (MAX_CANDIDATES + 1),
])
def test_rejects_invalid_candidates(candidates):
    with pytest.raises(SceneTravelError):
        normalize_candidates(candidates, remaining=128)


def test_export_import_is_source_bound_and_replay_verified():
    report = original_fork()
    bundle = export_market_fork(report)
    assert import_market_fork(bundle) == report
    for field in ("source_digest", "checkpoint_state_digest", "checksum"):
        forged = copy.deepcopy(bundle)
        forged[field] = "0" * 64
        with pytest.raises(SceneTravelError):
            import_market_fork(forged)


def test_cli_is_user_reachable_and_accepts_replayed_selected_save(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-fork", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert cli(["choose", "--report-json", json.dumps(report),
                "--candidate-id", "complete_delivery"]) == 0
    selected = json.loads(capsys.readouterr().out)
    assert selected["state"]["phase"] == "won"
    assert cli(["export", "--report-json", json.dumps(report)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert cli(["choose", "--report-json", json.dumps(report),
                "--candidate-id", "unearned_purchase"]) == 2
    assert "blocked" in capsys.readouterr().err


def test_rejects_duplicate_json_keys_and_oversized_plan(capsys):
    assert cli(["evaluate", "--session-json", '{"x":1,"x":2}',
                "--candidates-json", "[]"]) == 2
    assert "error" in capsys.readouterr().err
    source, _ = original_market()
    checkpoint = simulate_market(source, [])
    assert cli(["evaluate", "--session-json", json.dumps(checkpoint),
                "--candidates-json", " " * 131073]) == 2
    assert "error" in capsys.readouterr().err
