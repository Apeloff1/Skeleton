"""Tamper evidence, checkpoints, assignments, and protocol replay tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.worker_assignment import AssignmentConflict,WorkerAssignments
from skeleton.shells.worker_checkpoint import CheckpointChain,CheckpointError,WorkerCheckpoint
from skeleton.shells.worker_identity import WorkerIdentity,WorkerRegistry
from skeleton.shells.worker_journal import WorkerJournal,WorkerJournalEvent
from skeleton.shells.worker_protocol import ProtocolGuard,WorkerMessage,WorkerMessageKind


def identity(generation=1):
    return WorkerIdentity("w",generation)


def test_journal_append_links_digests():
    now=[0.0]
    journal=WorkerJournal(clock=lambda:now[0])
    first=journal.append(worker_id="w",generation=1,kind="start")
    now[0]=1
    second=journal.append(worker_id="w",generation=1,kind="stop")
    assert second.previous_digest==first.digest
    assert journal.verify().valid
    assert journal.head_digest==second.digest


def test_journal_filter_and_tail():
    journal=WorkerJournal()
    journal.append(worker_id="a",generation=1,kind="x")
    journal.append(worker_id="b",generation=1,kind="x")
    journal.append(worker_id="a",generation=1,kind="y")
    assert len(journal.events(worker_id="a"))==2
    assert len(journal.events(kind="x"))==2
    assert len(journal.tail(2))==2


def test_journal_capacity_bound():
    journal=WorkerJournal(max_events=1)
    journal.append(worker_id="w",generation=1,kind="x")
    with pytest.raises(RuntimeError):
        journal.append(worker_id="w",generation=1,kind="y")


def test_journal_tamper_is_detected():
    journal=WorkerJournal()
    event=journal.append(worker_id="w",generation=1,kind="x")
    journal._events[0]=replace(event,kind="tampered")
    verification=journal.verify()
    assert not verification.valid
    assert verification.first_invalid_sequence==1


def test_journal_previous_digest_tamper_detected():
    journal=WorkerJournal()
    journal.append(worker_id="w",generation=1,kind="x")
    event=journal.append(worker_id="w",generation=1,kind="y")
    journal._events[1]=replace(event,previous_digest="bad")
    assert not journal.verify().valid


def test_checkpoint_create_and_parse():
    checkpoint=WorkerCheckpoint.create(worker_id="w",generation=1,sequence=1)
    assert checkpoint.valid
    parsed=WorkerCheckpoint.from_dict(checkpoint.to_dict())
    assert parsed==checkpoint


def test_checkpoint_payload_tamper_rejected():
    checkpoint=WorkerCheckpoint.create(worker_id="w",generation=1,sequence=1)
    payload=checkpoint.to_dict()
    payload["completed_items"]=99
    with pytest.raises(CheckpointError):
        WorkerCheckpoint.from_dict(payload)


def test_checkpoint_chain_links_and_verifies():
    chain=CheckpointChain("w",1)
    first=chain.append(completed_items=1)
    second=chain.append(completed_items=2)
    assert second.previous_digest==first.digest
    assert chain.verify()
    assert chain.head==second


def test_checkpoint_chain_rejects_wrong_identity():
    chain=CheckpointChain("w",1)
    foreign=WorkerCheckpoint.create(worker_id="x",generation=1,sequence=1)
    with pytest.raises(CheckpointError):
        chain.restore(foreign)


def test_checkpoint_chain_rejects_rollback():
    chain=CheckpointChain("w",1)
    first=chain.append()
    with pytest.raises(CheckpointError):
        chain.restore(first)


def test_checkpoint_chain_rejects_fork():
    chain=CheckpointChain("w",1)
    chain.append()
    fork=WorkerCheckpoint.create(worker_id="w",generation=1,sequence=2,previous_digest="bad")
    with pytest.raises(CheckpointError):
        chain.restore(fork)


def make_assignments(now):
    workers=WorkerRegistry(clock=lambda:now[0])
    item=identity()
    workers.register(item)
    return workers,item,WorkerAssignments(workers,clock=lambda:now[0])


def test_assignment_assign_require_release():
    now=[0.0]
    _,item,assignments=make_assignments(now)
    assignment=assignments.assign("job",item,ttl_seconds=10)
    assert assignments.require(assignment)==assignment
    assert assignments.release(assignment)
    with pytest.raises(AssignmentConflict):
        assignments.require(assignment)


def test_assignment_conflict_same_item():
    now=[0.0]
    _,item,assignments=make_assignments(now)
    assignments.assign("job",item)
    with pytest.raises(AssignmentConflict):
        assignments.assign("job",item)


def test_assignment_expiry():
    now=[0.0]
    _,item,assignments=make_assignments(now)
    assignment=assignments.assign("job",item,ttl_seconds=5)
    now[0]=5
    with pytest.raises(AssignmentConflict):
        assignments.require(assignment)
    assert assignments.snapshot()==()


def test_assignment_renew_changes_revision():
    now=[0.0]
    _,item,assignments=make_assignments(now)
    assignment=assignments.assign("job",item)
    now[0]=1
    renewed=assignments.renew(assignment,ttl_seconds=10)
    assert renewed.revision==2
    assert renewed.assignment_id==assignment.assignment_id
    assert not assignments.release(assignment)
    assert assignments.release(renewed)


def test_assignment_generation_replacement_invalidates_old():
    now=[0.0]
    workers,item,assignments=make_assignments(now)
    assignment=assignments.assign("job",item)
    workers.replace(WorkerIdentity("w",2))
    with pytest.raises(Exception):
        assignments.require(assignment)


def message(sequence=1,generation=1,version=1,**kwargs):
    return WorkerMessage(
        message_id=f"m{sequence}",
        sequence=sequence,
        kind=kwargs.pop("kind",WorkerMessageKind.HEARTBEAT),
        sender=WorkerIdentity("w",generation),
        recipient="control",
        protocol_version=version,
        payload=kwargs.pop("payload",{}),
        **kwargs,
    )


def test_protocol_accepts_monotonic_sequence():
    guard=ProtocolGuard()
    guard.accept(message(1))
    cursor=guard.accept(message(2))
    assert cursor.last_sequence==2


def test_protocol_rejects_replay():
    guard=ProtocolGuard()
    guard.accept(message(1))
    with pytest.raises(RuntimeError,match="replay"):
        guard.accept(message(1))


def test_protocol_rejects_lower_sequence():
    guard=ProtocolGuard()
    guard.accept(message(2))
    with pytest.raises(RuntimeError):
        guard.accept(message(1))


def test_protocol_new_generation_can_restart_sequence():
    guard=ProtocolGuard()
    guard.accept(message(10,generation=1))
    cursor=guard.accept(message(1,generation=2))
    assert cursor.generation==2
    assert cursor.last_sequence==1


def test_protocol_rejects_generation_rollback():
    guard=ProtocolGuard()
    guard.accept(message(1,generation=2))
    with pytest.raises(RuntimeError,match="generation"):
        guard.accept(message(2,generation=1))


def test_protocol_rejects_version_mismatch():
    guard=ProtocolGuard(protocol_version=1)
    with pytest.raises(RuntimeError,match="version"):
        guard.accept(message(1,version=2))


def test_protocol_payload_must_be_json_shaped():
    with pytest.raises(ValueError):
        message(1,payload={"bad":object()})


def test_protocol_digest_stable():
    assert message(1,payload={"x":1}).digest==message(1,payload={"x":1}).digest
