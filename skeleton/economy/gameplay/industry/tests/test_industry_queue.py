"""Tick-driven build queue: timers, lines, chains, cancel and collect."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.industry.errors import JobRejected
from skeleton.economy.gameplay.industry.tests.conftest import (
    build_econ,
    build_system,
    stocked,
)


def test_build_runs_on_ticks_only(system):
    job = system.queue_build("ana", "smelt_ingot", 2, tick=5)
    assert job["status"] == "running" and job["start"] == 5 and job["end"] == 25
    assert system.econ.inventory("ana").count("ingot") == 0
    assert system.advance(24) == []
    done = system.advance(25)
    assert [j["job_id"] for j in done] == [job["job_id"]]
    assert system.econ.inventory("ana").count("ingot") == 2


def test_lines_limit_parallel_jobs_and_freed_line_starts_at_completion(system):
    system.set_lines("ana", 1)
    a = system.queue_build("ana", "smelt_ingot", 1, tick=0)
    b = system.queue_build("ana", "smelt_ingot", 1, tick=0)
    assert a["status"] == "running" and b["status"] == "queued"
    system.advance(1_000)  # one big step
    jobs = {j["job_id"]: j for j in system.jobs("ana")}
    assert jobs[b["job_id"]]["start"] == 10 and jobs[b["job_id"]]["end"] == 20


def test_advance_cadence_does_not_change_outcome():
    coarse, fine = stocked(), stocked()
    for s in (coarse, fine):
        s.set_lines("ana", 1)
        s.queue_chain("ana", "hull", 1, tick=0)
    coarse.advance(500)
    for t in range(1, 501):
        fine.advance(t)
    assert coarse.to_state()["queue"] == fine.to_state()["queue"]
    assert coarse.econ.snapshot() == fine.econ.snapshot()


def test_chain_runs_steps_in_dependency_order(system):
    chain = system.queue_chain("ana", "hull", 1, tick=0)
    assert len(chain["jobs"]) == 3
    system.advance(10_000)
    jobs = {j["job_id"]: j for j in system.jobs("ana")}
    smelt, press, weld = (jobs[i] for i in chain["jobs"])
    assert smelt["end"] <= press["start"] and press["end"] <= weld["start"]
    assert all(j["status"] == "delivered" for j in (smelt, press, weld))
    assert system.econ.inventory("ana").count("hull") == 1


def test_blocked_job_waits_for_materials():
    s = build_system()
    s.econ.grant("daily", "ana", tick=0)
    job = s.queue_build("ana", "smelt_ingot", 1, tick=0)
    assert job["status"] == "queued"
    s.econ.grant_items("stockpile", "ana", "ore", 4)
    s.econ.grant_items("stockpile", "ana", "coal", 2)
    s.advance(3)
    row = s.jobs("ana")[0]
    assert row["status"] == "running" and row["start"] == 3


def test_cancel_queued_cascades_to_dependents(system):
    system.set_lines("ana", 1)
    chain = system.queue_chain("ana", "hull", 1, tick=0)
    with pytest.raises(JobRejected):
        system.cancel("ana", chain["jobs"][0], tick=1)  # already running
    out = system.cancel("ana", chain["jobs"][1], tick=1)
    assert out["cancelled"] == [chain["jobs"][1], chain["jobs"][2]]
    system.advance(1_000)
    assert system.econ.inventory("ana").count("hull") == 0
    assert system.audit()["ok"]


def test_full_bags_hold_output_until_collect():
    econ = build_econ(slots=2)
    s = build_system(econ=econ)
    econ.grant("daily", "ana", tick=0)
    econ.grant_items("stockpile", "ana", "ore", 4)
    econ.grant_items("stockpile", "ana", "coal", 2)
    job = s.queue_build("ana", "smelt_ingot", 1, tick=0)
    econ.grant_items("stockpile", "ana", "plate", 1)
    econ.grant_items("stockpile", "ana", "hull", 1)
    s.advance(10)
    assert s.jobs("ana")[0]["status"] == "done"
    assert s.audit()["ok"]
    with pytest.raises(JobRejected):
        s.collect("ana", job["job_id"], tick=11)
    econ.consume_items("scrap", "ana", "hull", 1)
    assert s.collect("ana", job["job_id"], tick=12) == 1
    assert econ.inventory("ana").count("ingot") == 1
    with pytest.raises(JobRejected):
        s.collect("ana", job["job_id"], tick=13)


def test_refusals_change_nothing(system):
    before = system.digest()
    for call in (
        lambda: system.queue_build("ana", "nope", 1, tick=0),
        lambda: system.queue_build("zed", "smelt_ingot", 1, tick=0),
        lambda: system.queue_build("ana", "smelt_ingot", 0, tick=0),
        lambda: system.queue_build("ana", "smelt_ingot", 5_000, tick=0),
    ):
        with pytest.raises(Exception):
            call()
    assert system.digest() == before


def test_tick_cannot_go_backwards(system):
    system.advance(10)
    with pytest.raises(Exception):
        system.advance(9)
