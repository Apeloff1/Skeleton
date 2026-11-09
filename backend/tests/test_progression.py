import pytest

from core.progression import Medal, ProgressionState


def test_finish_records_personal_best_medal_ghost_and_unlock(tmp_path):
    state = ProgressionState(unlocked={"rim"})
    result = state.record_finish(
        "rim",
        score=42.5,
        medal=Medal.BRONZE,
        ghost=[{"t": 0.0, "x": 1}],
        distance=100,
        unlocks={"rim": ("bowl",)},
    )
    assert result.improved is True
    assert result.medal_improved is True
    assert result.newly_unlocked == ("bowl",)
    assert state.best["rim"] == 42.5
    assert state.medals["rim"] is Medal.BRONZE
    assert state.total_distance == 100


def test_slower_finish_does_not_replace_best_ghost_but_accumulates_distance():
    state = ProgressionState()
    state.record_finish("stage", score=10, medal=Medal.GOLD, ghost=[{"v": 1}], distance=4)
    result = state.record_finish("stage", score=11, medal=Medal.SILVER, ghost=[{"v": 2}], distance=3)
    assert result.improved is False
    assert result.medal_improved is False
    assert state.best["stage"] == 10
    assert state.ghosts["stage"] == [{"v": 1}]
    assert state.medals["stage"] is Medal.GOLD
    assert state.total_distance == 7


def test_faster_finish_replaces_best_and_ghost_without_downgrading_medal():
    state = ProgressionState()
    state.record_finish("stage", score=10, medal=Medal.GOLD, ghost=[{"v": 1}])
    result = state.record_finish("stage", score=9, medal=Medal.BRONZE, ghost=[{"v": 2}])
    assert result.improved is True
    assert result.medal_improved is False
    assert state.best["stage"] == 9
    assert state.ghosts["stage"] == [{"v": 2}]
    assert state.medals["stage"] is Medal.GOLD


def test_migration_merges_initial_unlocks_and_normalizes_snapshot():
    state = ProgressionState.migrate(
        {
            "version": 0,
            "best": {"a": 5},
            "medals": {"a": 2},
            "ghosts": {"a": [{"t": 1}]},
            "total_distance": 3,
            "unlocked": ["a"],
        },
        initial_unlocks={"free"},
    )
    assert state.version == 1
    assert state.unlocked == {"a", "free"}
    assert state.snapshot()["medals"] == {"a": 2}


def test_invalid_finish_metrics_rejected():
    state = ProgressionState()
    with pytest.raises(ValueError, match="cannot be negative"):
        state.record_finish("a", score=-1, medal=Medal.NONE)
    with pytest.raises(ValueError, match="cannot be negative"):
        state.record_finish("a", score=1, medal=Medal.NONE, distance=-1)
    with pytest.raises(ValueError, match="stage_id"):
        state.record_finish("", score=1, medal=Medal.NONE)
