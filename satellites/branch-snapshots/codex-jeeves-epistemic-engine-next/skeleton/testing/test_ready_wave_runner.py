"""Tests for ReadyWaveRunner — sync drain of SwarmDag ready waves."""

from __future__ import annotations

from skeleton.swarm import ReadyWaveRunner, SwarmDag, TaskStatus
from skeleton.swarm.dag import TaskNode


def _diamond(dag: SwarmDag) -> None:
    dag.submit("a", "root", {"n": "a"}, [])
    dag.submit("b", "mid", {"n": "b"}, ["a"])
    dag.submit("c", "mid", {"n": "c"}, ["a"])
    dag.submit("d", "sink", {"n": "d"}, ["b", "c"])


def test_drain_diamond_in_wave_order():
    dag = SwarmDag()
    _diamond(dag)
    order: list[str] = []

    def mark(task: TaskNode):
        order.append(task.id)
        return {"ok": task.id}

    runner = ReadyWaveRunner(dag)
    report = runner.drain(
        "exec-1",
        {"root": mark, "mid": mark, "sink": mark},
    )

    assert report.waves == 3
    assert report.failed == []
    assert report.completed[0] == "a"
    assert set(report.completed[1:3]) == {"b", "c"}
    assert report.completed[3] == "d"
    assert order == report.completed
    assert dag.get("d").status == TaskStatus.DONE
    assert report.stats["by_status"]["done"] == 4


def test_fail_does_not_unlock_dependents():
    dag = SwarmDag()
    dag.submit("a", "boom", {}, [])
    dag.submit("b", "ok", {}, ["a"])

    def explode(_task: TaskNode):
        raise RuntimeError("attestation denied")

    runner = ReadyWaveRunner(dag)
    report = runner.drain("exec-1", {"boom": explode, "ok": lambda t: {"ok": t.id}})

    assert "a" in report.failed
    assert "b" not in report.completed
    assert dag.get("a").status == TaskStatus.FAILED
    assert dag.get("b").status == TaskStatus.PENDING
    # Only one wave (root) — dependents never unlocked
    assert report.waves == 1


def test_unknown_capability_fails_cleanly():
    dag = SwarmDag()
    dag.submit("a", "missing_cap", {"x": 1}, [])
    dag.submit("b", "ok", {}, ["a"])

    runner = ReadyWaveRunner(dag)
    report = runner.run_available("exec-1", {"ok": lambda t: {"ok": True}})

    assert report.waves == 1
    assert report.completed == []
    assert report.failed == ["a"]
    assert dag.get("a").status == TaskStatus.FAILED
    assert dag.get("b").status == TaskStatus.PENDING

    # Further drain finds nothing
    empty = runner.drain("exec-1", {"ok": lambda t: {"ok": True}})
    assert empty.waves == 0
    assert empty.completed == []


def test_none_result_fails_not_complete():
    dag = SwarmDag()
    dag.submit("a", "cap", {}, [])

    runner = ReadyWaveRunner(dag)
    report = runner.run_available("e", {"cap": lambda _t: None})

    assert report.failed == ["a"]
    assert dag.get("a").status == TaskStatus.FAILED


def test_package_exports_swarm_dag():
    from skeleton import swarm

    assert swarm.SwarmDag is SwarmDag
    assert swarm.ReadyWaveRunner is ReadyWaveRunner
    assert hasattr(swarm, "TaskNode")
    assert hasattr(swarm, "TaskStatus")
    assert hasattr(swarm, "SubmitError")
