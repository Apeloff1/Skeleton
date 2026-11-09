"""Crash-safe repeated original game actions, restored from SQLite every cycle."""
import sqlite3
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile,author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_endurance import (
    EndurancePolicy,run_expedition_endurance,
)
from skeleton.jeeves.game_frontier_expedition_campaign import original_campaign_player
from skeleton.jeeves.game_frontier_expedition_save_store import ExpeditionSaveStore

SOURCE="f"*64


def world():
    return author_archipelago("endurance",SOURCE,ArchipelagoProfile(
        seed=5,islands=6,include_portals=True,
    ))


def test_repeat_actual_usable_gameplay_with_reopen_after_every_checkpoint(tmp_path):
    path=tmp_path/"endurance.sqlite"
    w=world()
    result=run_expedition_endurance(
        path,"run:01",w,original_campaign_player(),
        policy=EndurancePolicy(logical_cycles=12),
    )
    assert result["logical_cycles"]==12
    assert result["total_game_actions"]==60
    assert result["reopened_sqlite_sessions"]==12
    assert result["real_gameplay_replay_per_cycle"]
    assert not result["long_duration_qualification"]
    assert result["observed_wall_clock_days"]==0
    with ExpeditionSaveStore(path) as store:
        restored=store.load("run:01",w,original_campaign_player())
        assert restored.episode.position=="harbor"
        assert len(restored.episode.actions)==60
        assert restored.generation==13
        assert len(store.history("run:01"))==13
        assert restored.episode.health>0


def test_durable_endurance_receipts_are_monotonic_and_source_scoped(tmp_path):
    data=run_expedition_endurance(
        tmp_path/"chain.sqlite","run:02",world(),original_campaign_player(),
        policy=EndurancePolicy(logical_cycles=4),
    )
    rows=data["cycles"]
    assert [r["actual_actions"] for r in rows]==[5,10,15,20]
    assert [r["generation"] for r in rows]==[2,3,4,5]
    assert all(r["source_world"]==data["world_digest"] for r in rows)
    assert len({r["game_head"] for r in rows})==4
    assert len({r["receipt_digest"] for r in rows})==4


def test_missing_authored_rest_corridor_rejects_fake_endurance(tmp_path):
    world_without=author_archipelago("bad",SOURCE,ArchipelagoProfile(
        seed=5,islands=5,include_portals=False,
    ))
    with pytest.raises(ExpeditionError,match="reversible rest corridor"):
        run_expedition_endurance(
            tmp_path/"bad.sqlite","bad",world_without,
            original_campaign_player(),
            policy=EndurancePolicy(logical_cycles=1),
        )


def test_no_fake_months_or_years_reported_as_wall_clock_qualification(tmp_path):
    report=run_expedition_endurance(
        tmp_path/"clock.sqlite","run",world(),original_campaign_player(),
        policy=EndurancePolicy(logical_cycles=2),
    )
    assert report["reopened_sqlite_sessions"]==2
    assert report["observed_wall_clock_days"]==0
    assert not report["long_duration_qualification"]


@pytest.mark.parametrize("cycles",(0,366,1.5,True))
def test_endurance_cycle_budget_fails_closed(cycles):
    with pytest.raises(ExpeditionError,match="cycle count"):
        EndurancePolicy(logical_cycles=cycles)


def test_second_run_with_same_run_id_cannot_replay_extra_actions_silently(tmp_path):
    path=tmp_path/"duplicate.sqlite"
    w=world()
    run_expedition_endurance(
        path,"same",w,original_campaign_player(),
        policy=EndurancePolicy(logical_cycles=2),
    )
    with pytest.raises(ExpeditionError,match="lost or duplicated"):
        run_expedition_endurance(
            path,"same",w,original_campaign_player(),
            policy=EndurancePolicy(logical_cycles=2),
        )
