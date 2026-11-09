"""Tests for attested SwarmDag (sync port of gf-gameforge swarm.rs)."""

from __future__ import annotations

import pytest

from skeleton.swarm.dag import SubmitError, SwarmDag, TaskStatus


def test_ready_wave_roots_then_next_after_attested_complete():
    dag = SwarmDag()
    dag.submit("a", "cap", {"x": 1}, [])
    dag.submit("b", "cap", {"x": 2}, ["a"])
    dag.submit("c", "cap", {"x": 3}, ["a"])
    dag.submit("d", "cap", {"x": 4}, ["b", "c"])

    wave1 = dag.ready_wave()
    assert {n.id for n in wave1} == {"a"}
    assert dag.get("a").status == TaskStatus.READY
    assert dag.get("b").status == TaskStatus.PENDING

    assert dag.claim("a", "exec-1") is not None
    assert dag.complete("a", {"ok": True}) is True

    wave2 = dag.ready_wave()
    assert {n.id for n in wave2} == {"b", "c"}

    assert dag.claim("b", "exec-2") is not None
    assert dag.complete("b", {"ok": True}) is True
    # c still pending/ready — d must not unlock until both b and c done
    assert dag.ready_wave() == []  # c still Ready from wave2, not Pending

    assert dag.claim("c", "exec-3") is not None
    assert dag.complete("c", {"ok": True}) is True
    wave3 = dag.ready_wave()
    assert {n.id for n in wave3} == {"d"}


def test_unknown_dep_cycle_duplicate_rejected():
    dag = SwarmDag()
    dag.submit("a", "cap", {}, [])

    with pytest.raises(SubmitError) as unk:
        dag.submit("b", "cap", {}, ["missing"])
    assert unk.value.kind == "unknown_dependency"
    assert unk.value.detail == "missing"

    with pytest.raises(SubmitError) as cyc:
        dag.submit("loop", "cap", {}, ["loop"])
    assert cyc.value.kind == "cycle"

    with pytest.raises(SubmitError) as dup:
        dag.submit("a", "cap", {}, [])
    assert dup.value.kind == "duplicate"


def test_claim_only_ready_complete_only_running_with_result():
    dag = SwarmDag()
    dag.submit("a", "cap", {}, [])
    dag.submit("b", "cap", {}, ["a"])

    # claim before ready_wave → not Ready
    assert dag.claim("a", "e") is None

    wave = dag.ready_wave()
    assert len(wave) == 1
    assert dag.claim("a", "e1") is not None
    assert dag.get("a").status == TaskStatus.RUNNING
    assert dag.get("a").executor == "e1"

    # double claim rejected
    assert dag.claim("a", "e2") is None

    # complete without attestation (None) must not mark Done
    assert dag.complete("a", None) is False
    assert dag.get("a").status == TaskStatus.RUNNING

    # complete while not running
    assert dag.complete("b", {"x": 1}) is False

    assert dag.complete("a", {"attested": True}) is True
    assert dag.get("a").status == TaskStatus.DONE
    assert dag.get("a").result == {"attested": True}

    # attested complete unlocks dependents
    wave2 = dag.ready_wave()
    assert {n.id for n in wave2} == {"b"}
    assert dag.get("b").status == TaskStatus.READY


def test_fail_does_not_unlock_dependents():
    dag = SwarmDag()
    dag.submit("a", "cap", {}, [])
    dag.submit("b", "cap", {}, ["a"])

    dag.ready_wave()
    assert dag.claim("a", "e") is not None
    assert dag.fail("a") is True
    assert dag.get("a").status == TaskStatus.FAILED

    wave = dag.ready_wave()
    assert wave == []
    assert dag.get("b").status == TaskStatus.PENDING


def test_fail_only_on_running():
    dag = SwarmDag()
    dag.submit("a", "cap", {}, [])
    assert dag.fail("a") is False
    dag.ready_wave()
    assert dag.fail("a") is False  # Ready, not Running
    dag.claim("a", "e")
    assert dag.fail("a") is True


def test_stats_and_get():
    dag = SwarmDag()
    assert dag.get("nope") is None
    dag.submit("a", "cap", {"p": 1}, [])
    assert dag.stats()["tasks"] == 1
    dag.ready_wave()
    dag.claim("a", "e")
    dag.complete("a", 42)
    st = dag.stats()
    assert st["by_status"]["done"] == 1
