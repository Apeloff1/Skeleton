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
