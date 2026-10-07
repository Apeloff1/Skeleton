"""Tests for the Hierarchical Swarm Planner (Backlog I.3)."""
from __future__ import annotations

import time
import pytest

from core import swarm_planner as sp


def test_plan_full_coverage_default_phases():
    plan = sp.plan_build("b1", phases=[f"p{i:02d}" for i in range(1, 21)], seed=1)
    cov = plan["coverage"]
    assert cov["all_covered"] is True
    assert cov["coverage_pct"] == 100.0
    assert cov["phases_covered"] == cov["phases_total"] == 20
    assert cov["missing_phases"] == []
    assert cov["empty_platoons"] == []


def test_four_tiers_present():
    plan = sp.plan_build("b1", phases=["p01", "p02"], seed=1)
    tiers = {n["tier"] for n in plan["nodes"]}
    assert tiers == {"director", "lead", "platoon"}  # workers nested under platoon
    assert plan["tiers"] == ["director", "lead", "platoon", "worker"]
    # exactly one director, one platoon per phase
    assert sum(1 for n in plan["nodes"] if n["tier"] == "director") == 1
    assert sum(1 for n in plan["nodes"] if n["tier"] == "platoon") == 2


def test_every_platoon_has_workers():
    plan = sp.plan_build("b1", phases=[f"p{i:02d}" for i in range(1, 11)], seed=5, platoon_size=6)
    for n in plan["nodes"]:
        if n["tier"] == "platoon":
            assert n["size"] >= 1
            assert len(n["workers"]) == n["size"]


def test_determinism_same_seed():
    a = sp.plan_build("b1", phases=["p01", "p02", "p03"], seed=7, platoon_size=4)
    b = sp.plan_build("b1", phases=["p01", "p02", "p03"], seed=7, platoon_size=4)
    assert a["plan_hash"] == b["plan_hash"]
    assert a["worker_assignments"] == b["worker_assignments"]


def test_different_seed_changes_plan():
    a = sp.plan_build("b1", phases=["p01", "p02", "p03"], seed=7)
    b = sp.plan_build("b1", phases=["p01", "p02", "p03"], seed=8)
    assert a["plan_hash"] != b["plan_hash"]


def test_default_sequential_waves():
    plan = sp.plan_build("b1", phases=["p01", "p02", "p03"], seed=1)
    waves = [w["phases"] for w in plan["waves"]]
    assert waves == [["p01"], ["p02"], ["p03"]]
    assert plan["critical_path_len"] == 3


def test_custom_deps_parallel_waves():
    plan = sp.plan_build("b1", phases=["a", "b", "c"], deps={"c": ["a", "b"]}, seed=1)
    waves = [set(w["phases"]) for w in plan["waves"]]
    assert waves[0] == {"a", "b"}
    assert waves[1] == {"c"}
    assert plan["critical_path_len"] == 2


def test_cycle_rejected():
    with pytest.raises(ValueError):
        sp.plan_build("b1", phases=["a", "b"], deps={"a": ["b"], "b": ["a"]})


def test_unknown_dep_rejected():
    with pytest.raises(ValueError):
        sp.plan_build("b1", phases=["a"], deps={"a": ["zzz"]})


def test_duplicate_phase_rejected():
    with pytest.raises(ValueError):
        sp.plan_build("b1", phases=["a", "a"])


def test_verify_plan_valid():
    plan = sp.plan_build("b1", phases=[f"p{i:02d}" for i in range(1, 13)], seed=3)
    v = sp.verify_plan(plan)
    assert v["valid"] is True
    assert v["acyclic"] and v["fully_reachable"] and v["coverage_ok"]
    assert v["problems"] == []


def test_verify_detects_uncovered_phase():
    plan = sp.plan_build("b1", phases=["p01", "p02"], seed=1)
    # sabotage: drop a platoon node so a phase is uncovered
    plan["nodes"] = [n for n in plan["nodes"] if n.get("phase_id") != "p02"]
    plan["coverage"] = sp._coverage(plan, ["p01", "p02"])
    v = sp.verify_plan(plan)
    assert v["valid"] is False
    assert v["coverage_ok"] is False


def test_lead_load_balanced():
    plan = sp.plan_build("b1", phases=[f"p{i:02d}" for i in range(1, 21)], seed=1)
    loads = list(plan["lead_load"].values())
    # 20 phases across 5 leads → 4 each, perfectly balanced
    assert max(loads) - min(loads) <= 1
    assert sum(loads) == 20


def test_topo_waves_directly():
    waves = sp.topo_waves(["a", "b", "c", "d"], {"b": ["a"], "c": ["a"], "d": ["b", "c"]})
    assert waves[0] == ["a"]
    assert set(waves[1]) == {"b", "c"}
    assert waves[2] == ["d"]


# ── Scheduler (live DAG execution) — pure core, DB-free ──────────────────
from core import swarm_scheduler as sch  # noqa: E402


def _fake_exec_recorder(order):
    def ex(phase_id, prev_handoff, rotation_idx, wave):
        order.append((phase_id, prev_handoff, rotation_idx, wave))
        return {"handoff": f"HO[{phase_id}]", "members": [{"code": f"W{rotation_idx}"}],
                "whisper_count": 1, "transcript": [1, 2]}
    return ex


def test_scheduler_runs_all_phases_in_wave_order():
    plan = sp.plan_build("b", phases=["p01", "p02", "p03"], seed=1)
    order = []
    res = sch.run_with_executor(plan, _fake_exec_recorder(order))
    assert res["execution_complete"] is True
    assert res["phases_executed"] == 3
    assert [o[0] for o in order] == ["p01", "p02", "p03"]
    assert res["missing"] == []


def test_scheduler_passes_upstream_handoffs():
    plan = sp.plan_build("b", phases=["a", "b", "c"], deps={"c": ["a", "b"]}, seed=1)
    order = []
    res = sch.run_with_executor(plan, _fake_exec_recorder(order))
    # c should run last and receive a+b handoffs merged
    last = [o for o in order if o[0] == "c"][0]
    assert "HO[a]" in last[1] and "HO[b]" in last[1]
    assert res["wave_count"] == 2


def test_scheduler_deps_from_plan():
    plan = sp.plan_build("b", phases=["a", "b"], seed=1)  # default chain b<-a
    deps = sch.deps_from_plan(plan)
    assert deps["b"] == ["a"]
    assert deps["a"] == []


def test_execute_schedule_caps_phases():
    big = [f"p{i:02d}" for i in range(1, sch.MAX_LIVE_PHASES + 5)]
    with pytest.raises(ValueError):
        sch.execute_schedule("b", phases=big, persist=False)


def test_participation_stats():
    plan = sp.plan_build("b", phases=["p01", "p02", "p03"], seed=1)
    order = []
    res = sch.run_with_executor(plan, _fake_exec_recorder(order))
    ps = sch.participation_stats(res)
    # fake executor emits one member 'W{rotation}' per phase → 3 distinct, no legion meta
    assert ps["distinct_agents"] == 3
    assert ps["total_seats"] == 3
    assert "legion_balance_pct" in ps


def test_build_stages_constant():
    assert "questionnaire" in sch.BUILD_STAGES
    assert "launch" == sch.BUILD_STAGES[-1]
    assert len(sch.BUILD_STAGES) == 13


def test_async_job_lifecycle():
    jid = sch.start_async("execute", build_id="async_test",
                          phases=["p01", "p02"], seed=1, platoon_size=3, persist=False)
    assert isinstance(jid, str) and len(jid) == 16
    # poll up to ~5s for completion
    for _ in range(50):
        j = sch.get_job(jid)
        if j and j["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    j = sch.get_job(jid)
    assert j["status"] == "done", j.get("error")
    assert j["result"]["coverage"]["all_covered"] is True
    assert "participation" in j["result"]
