"""End-to-end and adversarial time-trial acceptance for Lantern Quay."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_time_trials import (
    time_trial_report, verify_time_trial_report, resume_time_trial,
    time_trial_leaderboard, verify_time_trial_leaderboard, validate_course,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def world():
    return load_source(ROOT / "harbor_lantern_quay.json")


def course():
    return decode((ROOT / "harbor_lantern_quay_time_trial.json").read_bytes())


def bundle():
    return export_bundle(world(), demo_actions(), require_win=True)


def test_full_original_game_earns_all_four_checkpoint_visits_and_gold():
    report = time_trial_report(bundle(), course(), require_finish=True)
    assert report["status"] == "finished"
    assert report["medal"] == "gold"
    assert report["finish_tick"] == 18
    assert [entry["id"] for entry in report["visits"]] == [
        "timber", "ore", "pantry", "dock_approach",
    ]
    assert [entry["tick"] for entry in report["visits"]] == [1, 4, 9, 16]
    assert verify_time_trial_report(decode(canonical(report)), require_finish=True)[
        "terminal_digest"
    ] == bundle()["terminal_digest"]
    assert canonical(time_trial_report(bundle(), course())) == canonical(report)


def test_partial_save_is_portable_and_never_claims_medal():
    partial = export_bundle(world(), demo_actions()[:8])
    report = time_trial_report(partial, course())
    assert report["status"] == "incomplete"
    assert report["medal"] is None
    assert report["finish_tick"] is None
    assert len(report["visits"]) == 2
    assert verify_time_trial_report(report)["status"] == "incomplete"
    with pytest.raises(HarborError, match="finish not earned"):
        time_trial_report(partial, course(), require_finish=True)


def test_checkpoint_resume_uses_expected_digest_and_replays_full_run():
    original = export_bundle(world(), demo_actions()[:8])
    continued = resume_time_trial(
        original, course(), demo_actions()[8:],
        expected_terminal_digest=original["terminal_digest"], require_finish=True,
    )
    assert continued == time_trial_report(bundle(), course(), require_finish=True)
    with pytest.raises(HarborError, match="stale"):
        resume_time_trial(
            original, course(), demo_actions()[8:],
            expected_terminal_digest="0" * 64,
        )


def test_earned_ending_choice_is_part_of_course_contract():
    shelter = demo_actions()
    shelter[-1] = {"op": "choose", "choice": "shelter"}
    report = time_trial_report(export_bundle(world(), shelter), course())
    assert report["status"] == "incomplete"
    assert report["medal"] is None


def test_missed_checkpoint_and_late_finish_cannot_earn_medal():
    changed = deepcopy(course())
    changed["checkpoints"][1]["latest_tick"] = 3
    changed["checkpoints"][2]["latest_tick"] = 12
    report = time_trial_report(bundle(), changed)
    assert report["status"] == "incomplete"
    assert [v["id"] for v in report["visits"]] == ["timber"]
    late = deepcopy(course())
    late["deadline"] = 17
    late["medals"] = {"gold": 10, "silver": 14, "bronze": 17}
    late["checkpoints"][-1]["latest_tick"] = 17
    assert time_trial_report(bundle(), late)["status"] == "incomplete"


@pytest.mark.parametrize("mutation", [
    lambda c: c.update({"source_id": "foreign-world"}),
    lambda c: c["checkpoints"][0].update({"at": [0, 0]}),
    lambda c: c["checkpoints"][0].update({"latest_tick": True}),
    lambda c: c["checkpoints"][1].update({"id": "timber"}),
    lambda c: c["checkpoints"][1].update({"at": [2, 1]}),
    lambda c: c["medals"].update({"silver": 18}),
    lambda c: c["medals"].update({"bronze": 33}),
    lambda c: c.update({"deadline": 10000}),
    lambda c: c.update({"choice": "unsafe"}),
    lambda c: c.update({"extra": 1}),
])
def test_malformed_authored_courses_fail_closed(mutation):
    authored = course()
    mutation(authored)
    with pytest.raises(HarborError):
        validate_course(authored, world())


@pytest.mark.parametrize("mutation", [
    lambda r: r.update({"medal": "gold"}),
    lambda r: r.update({"finish_tick": 1}),
    lambda r: r["visits"][0].update({"tick": 0}),
    lambda r: r["visits"][0].update({"event_digest": "0" * 64}),
    lambda r: r["bundle"]["state"].update({"coins": 999}),
    lambda r: r["course"]["checkpoints"][0].update({"at": [5, 3]}),
])
def test_outer_digest_resealing_cannot_forge_time_trial(mutation):
    report = time_trial_report(bundle(), course())
    mutation(report)
    report["report_digest"] = digest({
        k: v for k, v in report.items() if k != "report_digest"
    })
    with pytest.raises(HarborError):
        verify_time_trial_report(report)


def test_leaderboard_ranks_verified_play_and_rejects_duplicate_replays():
    first = time_trial_report(bundle(), course(), require_finish=True)
    slower_actions = [{"op": "wait"}] + demo_actions()
    slower = time_trial_report(export_bundle(world(), slower_actions), course(), require_finish=True)
    board = time_trial_leaderboard([slower, first])
    assert [row["finish_tick"] for row in board["ranking"]] == [18, 19]
    assert [row["rank"] for row in verify_time_trial_leaderboard(board)] == [1, 2]
    with pytest.raises(HarborError, match="duplicate"):
        time_trial_leaderboard([first, deepcopy(first)])
    with pytest.raises(HarborError):
        time_trial_leaderboard([first] * 9)


def test_leaderboard_forged_rank_and_source_rejected_after_resealing():
    first = time_trial_report(bundle(), course())
    board = time_trial_leaderboard([first])
    board["ranking"][0]["finish_tick"] = 1
    board["board_digest"] = digest({k: v for k, v in board.items() if k != "board_digest"})
    with pytest.raises(HarborError, match="replay mismatch"):
        verify_time_trial_leaderboard(board)
    other = deepcopy(course())
    other["medals"] = {"gold": 17, "silver": 23, "bronze": 32}
    with pytest.raises(HarborError, match="incompatible"):
        time_trial_leaderboard([first, time_trial_report(bundle(), other, require_finish=True)])


def test_cli_source_to_run_to_portable_report_to_replay_verification(tmp_path):
    path = tmp_path / "save.json"
    path.write_bytes(canonical(bundle()))
    trial = ROOT / "harbor_lantern_quay_time_trial.json"
    produced = subprocess.run(
        CLI + ["trial-run", "--bundle", str(path), "--trial", str(trial), "--require-win"],
        capture_output=True, check=False,
    )
    assert produced.returncode == 0, produced.stderr.decode()
    report = decode(produced.stdout)
    assert report["medal"] == "gold"
    report_path = tmp_path / "trial.json"
    report_path.write_bytes(produced.stdout)
    verified = subprocess.run(
        CLI + ["trial-verify", "--report", str(report_path), "--require-win"],
        capture_output=True, check=False,
    )
    assert verified.returncode == 0, verified.stderr.decode()
    assert decode(verified.stdout)["medal"] == "gold"
    report["visits"][0]["tick"] = 99
    report_path.write_bytes(canonical(report))
    failed = subprocess.run(
        CLI + ["trial-verify", "--report", str(report_path)],
        capture_output=True, check=False,
    )
    assert failed.returncode == 2
    assert failed.stdout == b""
