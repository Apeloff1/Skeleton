"""Crash-before-write and crash-after-commit replay on actual SQLite game saves."""
from dataclasses import replace
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile,author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_campaign import original_campaign_player
from skeleton.jeeves.game_frontier_expedition_save_store import ExpeditionSaveStore
from skeleton.jeeves.game_frontier_expedition_crash import (
    CrashPolicy,exercise_game_crash_recovery,
)


def game():
    w=author_archipelago(
        "recover","f"*64,ArchipelagoProfile(seed=34,islands=5),
    )
    return w,original_campaign_player()


def test_crash_before_commit_and_after_commit_resume_exactly_once(tmp_path):
    w,p=game()
    path=tmp_path/"faults.sqlite"
    report=exercise_game_crash_recovery(
        path,w,p,policy=CrashPolicy(
            game_cycles=5,crash_before_commit_every=3,
            crash_after_commit_every=4,
        ),
    )
    assert report["game_actions"]==25
    assert report["sqlite_generations"]==26
    assert report["injected_crashes"]>0
    assert report["reconciled_lost_acks"]>0
    assert report["exactly_once_gameplay_replayed"]
    assert not report["real_process_crashes_observed"]
    assert not report["release_approved"]
    with ExpeditionSaveStore(path) as store:
        checkpoint=store.load("crash_qualification",w,p)
        assert checkpoint.generation==26
        assert len(checkpoint.episode.actions)==25
        assert checkpoint.episode.position==w.arrival
        assert checkpoint.episode.health>0


def test_crash_replay_attests_new_game_generations_without_duplicate_actions(tmp_path):
    w,p=game()
    report=exercise_game_crash_recovery(
        tmp_path/"fault.sqlite",w,p,
        policy=CrashPolicy(
            game_cycles=2,crash_before_commit_every=2,
            crash_after_commit_every=3,
        ),
    )
    assert report["game_actions"]==10
    assert report["sqlite_generations"]==11
    assert report["faults"]
    assert {entry["effect"] for entry in report["faults"]}=={
        "crash_before_commit","crash_after_commit_before_ack",
        "recovered_committed_action","acknowledged",
    }
    assert report["history_head"]
    assert len(report["receipt_digest"])==64


def test_existing_savefile_cannot_be_overwritten_by_crash_lab(tmp_path):
    w,p=game()
    root=tmp_path/"used.sqlite"
    root.write_text("existing game",encoding="utf-8")
    with pytest.raises(ExpeditionError,match="refuses"):
        exercise_game_crash_recovery(root,w,p)
    assert root.read_text(encoding="utf-8")=="existing game"


@pytest.mark.parametrize("bad",(
    {"game_cycles":0},{"game_cycles":101},
    {"crash_before_commit_every":0},
    {"crash_after_commit_every":1001},
    {"max_retries_per_action":0},
))
def test_crash_safety_budget_must_be_explicit_and_bounded(bad):
    with pytest.raises(ExpeditionError,match="safety budget"):
        CrashPolicy(**bad)


def test_recovered_fault_report_is_same_for_same_seed_and_policy(tmp_path):
    w,p=game()
    a=exercise_game_crash_recovery(
        tmp_path/"a.sqlite",w,p,policy=CrashPolicy(game_cycles=3))
    b=exercise_game_crash_recovery(
        tmp_path/"b.sqlite",w,p,policy=CrashPolicy(game_cycles=3))
    assert a==b
    assert a["last_receipt"] if "last_receipt" in a else a["history_head"]
