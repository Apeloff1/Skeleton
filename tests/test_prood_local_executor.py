"""Actual local computation, dependency receipts, and authenticated inventory."""
import sqlite3
from dataclasses import replace
from hashlib import sha256

import pytest

from skeleton.frontier.durable_work import (
    DurableWorkJournal, WorkConflict, WorkIntegrityError, WorkOrder, work_identity,
)
from skeleton.frontier.worker_results import WorkerResultStore, ResultConflict, ResultIntegrityError
from skeleton.prood.admission import admit_build
from skeleton.prood.local_executor import ComputedResult, LocalWorkerExecutor
from skeleton.prood.supervisor import ProodSupervisor


def stores(path):
    work_db = sqlite3.connect(path / "work.db")
    result_db = sqlite3.connect(path / "result.db")
    return (work_db, result_db,
            DurableWorkJournal(work_db, scope="tenant", custody_key=b"w"*32),
            WorkerResultStore(result_db, scope="tenant", key=b"o"*32))


def test_inventory_detects_deleted_row_and_missing_dependency(tmp_path):
    db, out, work, results = stores(tmp_path)
    a = work_identity("tenant", "task", "a")
    b = work_identity("tenant", "task", "b")
    work.submit([WorkOrder(a,"task",{}), WorkOrder(b,"task",{},(a,))])
    first = work.inventory()
    assert first.count == 2 and first.ready == (a,) and first.blocked == (b,)
    claim = work.claim(a,owner="worker")
    assert work.inventory().unresolved == (a,)
    work.finish(claim,succeeded=True,receipt_digest="a"*64)
    assert work.inventory().ready == (b,)
    with pytest.raises(WorkIntegrityError):
        work.inventory(expected_digest=first.digest)
    db.execute("DELETE FROM frontier_work_orders_v1 WHERE work_id=?", (a,))
    db.commit()
    with pytest.raises(WorkIntegrityError,match="missing dependency"):
        work.inventory()
    db.close()
    out.close()


def test_result_replay_is_immutable_and_tamper_fails(tmp_path):
    db, out, work, results = stores(tmp_path)
    wid = "a"*64
    receipt = results.publish(wid,digest="b"*64,succeeded=True,output={"n":[1]})
    receipt.output["n"].append(999)
    assert results.load(wid).output == {"n":[1]}
    assert results.publish(wid,digest="b"*64,succeeded=True,output={"n":[1]}).receipt_digest == receipt.receipt_digest
    with pytest.raises(ResultConflict):
        results.publish(wid,digest="b"*64,succeeded=False,output={})
    out.execute("UPDATE frontier_worker_results_v1 SET body=?", (b'{}',))
    out.commit()
    with pytest.raises(ResultIntegrityError):
        results.load(wid)
    db.close()
    out.close()


@pytest.mark.asyncio
async def test_real_computation_consumes_durable_dependency_outputs(tmp_path):
    db, out, work, results = stores(tmp_path)
    context = {"regions": 4}
    plan = admit_build(work, build_id="game", phases=["world","mechanics"],
                       platoon_size=2, game_ctx=context)
    async def world(data):
        return ComputedResult(True, {"regions": data.game_context["regions"] + data.seat})
    async def systems(data):
        return ComputedResult(True, {"complexity": sum(value["regions"] for _, value in data.dependency_results)})
    class Policy:
        def allow(self, _):
            return True
    executor = LocalWorkerExecutor(work, results,game_context=context,handlers={"world":world,"systems":systems})
    supervisor = ProodSupervisor(work,Policy(),executor,owner="operator")
    first = await supervisor.dispatch()
    assert len(first.completed)==2
    second = await supervisor.dispatch()
    assert len(second.completed)==2
    for item in second.completed:
        result = results.load(item.work_id)
        assert result.output == {"complexity":11}
        assert result.receipt_digest == item.receipt
    assert dict(work.inventory().states)["succeeded"]==4
    db.close()
    out.close()


@pytest.mark.asyncio
async def test_worker_context_mismatch_never_invokes_handler(tmp_path):
    db, out, work, results = stores(tmp_path)
    plan = admit_build(work,build_id="game",phases=["world"],platoon_size=1,game_ctx={"a":1})
    claim=work.claim(plan.work[0].work_id,owner="operator")
    async def handler(_):
        pytest.fail("wrong context was dispatched")
    executor=LocalWorkerExecutor(work,results,game_context={"a":2},handlers={"world":handler})
    with pytest.raises(WorkConflict):
        await executor.execute_and_commit(claim)
    assert results.load(claim.work_id) is None
    assert work.status(claim.work_id).state == "claimed"
    db.close()
    out.close()


@pytest.mark.asyncio
async def test_incompatible_plan_stays_pending_instead_of_being_claimed(tmp_path):
    db, out, work, results = stores(tmp_path)
    plan = admit_build(work, build_id="foreign", phases=["world"], platoon_size=1, game_ctx={"a":1})
    async def handler(_):
        pytest.fail("unsupported plan must not run")
    class Policy:
        def allow(self, _):
            return True
    executor = LocalWorkerExecutor(work, results, game_context={"a":2}, handlers={"world":handler})
    report = await ProodSupervisor(work, Policy(), executor, owner="operator").dispatch()
    assert report.claimed == 0 and report.denied == (plan.work[0].work_id,)
    assert work.status(plan.work[0].work_id).state == "pending"
    db.close()
    out.close()


@pytest.mark.asyncio
async def test_result_survives_crash_window_without_reexecution(tmp_path):
    from skeleton.prood.recovery_review import review_worker_result
    db, out, work, results = stores(tmp_path)
    plan = admit_build(work, build_id="restart", phases=["world"], platoon_size=1)
    wid = plan.work[0].work_id
    claim = work.claim(wid, owner="operator")
    calls = []
    async def handler(data):
        calls.append(data.work_id)
        return ComputedResult(True, {"region": data.seat})
    executor = LocalWorkerExecutor(work, results, game_context={}, handlers={"world":handler})
    outcome = await executor.execute_and_commit(claim)
    assert work.status(wid).state == "claimed"
    db.close()
    out.close()
    db, out, work, results = stores(tmp_path)
    review = review_worker_result(work, results, wid)
    assert review.proposed_state == "succeeded"
    assert review.receipt_digest == outcome.receipt_digest
    assert not review.independent_quiescence_verified
    assert work.ready() == ()
    # No execution is triggered by recovery inspection.
    assert calls == [wid]
    assert work.status(wid).state == "claimed"
    db.close()
    out.close()


def test_private_result_reopen_and_explicit_creation(tmp_path):
    import os
    from skeleton.app.offline_custody import open_worker_results
    if os.name != "posix":
        pytest.skip("canonical private SQLite POSIX custody")
    tmp_path.chmod(0o700)
    with open_worker_results(tmp_path, scope="tenant", key=b"z"*32, create=True) as store:
        first = store.publish("a"*64, digest="b"*64, succeeded=True, output={"regions": [1,2]})
    with open_worker_results(tmp_path, scope="tenant", key=b"z"*32, create=False) as store:
        assert store.load("a"*64) == first
    with pytest.raises(FileExistsError):
        with open_worker_results(tmp_path, scope="tenant", key=b"z"*32, create=True):
            pass


def test_recovery_rejects_authenticated_result_for_wrong_input(tmp_path):
    from skeleton.prood.recovery_review import review_worker_result
    db, out, work, results = stores(tmp_path)
    plan = admit_build(work, build_id="wrong-input", phases=["world"], platoon_size=1)
    wid = plan.work[0].work_id
    work.claim(wid, owner="operator")
    results.publish(wid, digest="0"*64, succeeded=True, output={"wrong":True})
    with pytest.raises(WorkConflict, match="original claimed input"):
        review_worker_result(work, results, wid)
    assert work.status(wid).state == "claimed"
    db.close()
    out.close()
