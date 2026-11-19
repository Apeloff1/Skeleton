"""Independent recovery, durable delivery and supervised Prood dispatch."""
import sqlite3
from dataclasses import replace

import pytest

from skeleton.frontier.durable_work import (
    DurableWorkJournal, WorkConflict, WorkOrder, sign_recovery, work_identity,
)
from skeleton.frontier.durable_outbox import DurableOutbox, DestinationAcknowledgement, OutboxMessage
from skeleton.prood.admission import admit_build
from skeleton.prood.supervisor import ProodSupervisor, WorkerOutcome


def journal(path):
    db = sqlite3.connect(path)
    return db, DurableWorkJournal(db, scope="owner", custody_key=b"c" * 32,
                                  recovery_key=b"r" * 32)


def test_recovery_cannot_reissue_uncertain_work(tmp_path):
    db, store = journal(tmp_path / "queue.sqlite")
    wid = work_identity("owner", "task", "identity")
    store.submit([WorkOrder(wid, "task", {})])
    store.claim(wid, owner="worker")
    challenge = store.recovery_challenge(wid)
    proof = sign_recovery(challenge, state="uncertain", receipt_digest="a" * 64,
                          recovery_key=b"r" * 32)
    with pytest.raises(WorkConflict):
        store.reconcile_claimed(replace(proof, receipt_digest="b" * 64))
    assert store.reconcile_claimed(proof).state == "uncertain"
    with pytest.raises(WorkConflict):
        store.reconcile_claimed(proof)
    with pytest.raises(WorkConflict):
        store.claim(wid, owner="other")
    db.close()


def test_durable_outbox_requires_independently_verified_receipt(tmp_path):
    db, store = journal(tmp_path / "queue.sqlite")
    outbox = DurableOutbox(store)
    original = OutboxMessage("id", "receiver", {"payload": [1]})
    pending = outbox.enqueue(original)
    assert outbox.enqueue(original) == pending
    with pytest.raises(WorkConflict):
        outbox.enqueue(OutboxMessage("id", "receiver", {"changed": True}))
    claim = outbox.claim(pending.work_id, owner="sender")
    ack = DestinationAcknowledgement("id", "receiver", claim.message_digest, "a" * 64)
    with pytest.raises(WorkConflict):
        outbox.acknowledge(claim, ack, verify_acknowledgement=lambda _: False)
    with pytest.raises(WorkConflict):
        outbox.acknowledge(claim, replace(ack, destination="foreign"),
                           verify_acknowledgement=lambda _: True)
    result = outbox.acknowledge(claim, ack, verify_acknowledgement=lambda _: True)
    assert result.state == "succeeded"
    assert outbox.ready() == ()
    db.close()


@pytest.mark.asyncio
async def test_supervisor_fences_dependency_stages_and_policy_denial(tmp_path):
    db, store = journal(tmp_path / "queue.sqlite")
    admission = admit_build(store, build_id="game", phases=["world", "mechanics"], platoon_size=3)

    class Policy:
        permit = False
        def allow(self, work):
            return self.permit

    class Executor:
        async def execute_and_commit(self, claim):
            return WorkerOutcome(claim.work_id, True, "c" * 64)

    policy = Policy()
    supervisor = ProodSupervisor(store, policy, Executor(), owner="supervisor")
    denied = await supervisor.dispatch()
    assert denied.claimed == 0 and len(denied.denied) == 3
    policy.permit = True
    first = await supervisor.dispatch()
    assert len(first.completed) == 3
    assert {row.work_id for row in first.completed} == {row.work_id for row in admission.work[:3]}
    following = await supervisor.dispatch()
    assert len(following.completed) == 3
    assert store.ready() == ()
    db.close()


@pytest.mark.asyncio
async def test_supervisor_never_retries_ambiguous_exception(tmp_path):
    db, store = journal(tmp_path / "queue.sqlite")
    admit_build(store, build_id="game", phases=["world"], platoon_size=1)

    class Policy:
        def allow(self, work):
            return True

    class FailsAfterPossibleWrite:
        calls = 0
        async def execute_and_commit(self, claim):
            self.calls += 1
            raise OSError("outcome unknown")

    worker = FailsAfterPossibleWrite()
    supervisor = ProodSupervisor(store, Policy(), worker, owner="supervisor")
    first = await supervisor.dispatch()
    assert len(first.uncertain) == 1
    assert store.status(first.uncertain[0]).state == "claimed"
    second = await supervisor.dispatch()
    assert second.claimed == 0 and worker.calls == 1
    db.close()


def test_forged_delivery_and_mutated_claim_cannot_publish(tmp_path):
    db, store = journal(tmp_path / "queue.sqlite")
    outbox = DurableOutbox(store)
    pending = outbox.enqueue(OutboxMessage("id", "receiver", {"payload": [1]}))
    delivery = outbox.claim(pending.work_id, owner="sender")
    ack = DestinationAcknowledgement("id", "receiver", delivery.message_digest, "a" * 64)
    forged = replace(delivery, message=OutboxMessage("id", "receiver", {"payload": [2]}))
    called = []
    with pytest.raises(WorkConflict):
        outbox.acknowledge(forged, ack, verify_acknowledgement=lambda _: called.append(True))
    assert not called
    delivery.claim.payload["payload"]["payload"].append(2)
    with pytest.raises(WorkConflict):
        store.finish(delivery.claim, succeeded=True, receipt_digest="a" * 64)
    assert store.status(pending.work_id).state == "claimed"
    db.close()
