import pytest

from core.shift_supervisor.planning_harness import run_planning_harness


def test_planning_harness_exercises_thousand_worker_peak_loop():
    report = run_planning_harness(total_workers=1000, cycles=4)

    assert report["ok"] is True
    assert report["workers"] == 1000
    assert report["virtual_minutes"] == 60
    assert report["secretary_calls"] == 4
    assert report["manager_calls"] == 2
    assert report["unique_plan_items"] == 4
    assert report["revision_count"] == 6
    assert report["attention_workers"] <= 64
    assert all(report["invariants"].values())
    assert all(cycle["worker_count"] == 1000 for cycle in report["cycles"])

    night_members = set(report["claims"]["night"]["members"].values())
    idle_members = set(report["claims"]["idle"]["members"].values())
    assert len(night_members) == 4
    assert len(idle_members) == 4
    assert night_members.isdisjoint(idle_members)
    assert report["claims"]["night"]["task_id"] != report["claims"]["idle"]["task_id"]
    assert report["claims"]["overtime_worker"] not in night_members


def test_planning_harness_preserves_15_30_cadence_for_odd_cycle_count():
    report = run_planning_harness(total_workers=10, cycles=5)

    assert report["secretary_calls"] == 5
    assert report["manager_calls"] == 3
    assert report["revision_count"] == 8
    assert [cycle["actors"] for cycle in report["cycles"]] == [
        ["secretary", "manager"],
        ["secretary"],
        ["secretary", "manager"],
        ["secretary"],
        ["secretary", "manager"],
    ]


@pytest.mark.parametrize(
    ("workers", "cycles", "message"),
    [
        (3, 4, "total_workers"),
        (10, 0, "cycles"),
    ],
)
def test_planning_harness_rejects_invalid_bounds(workers, cycles, message):
    with pytest.raises(ValueError, match=message):
        run_planning_harness(total_workers=workers, cycles=cycles)