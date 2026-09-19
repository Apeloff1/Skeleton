"""Exhaustive workspace transaction state-machine transition matrix."""

from __future__ import annotations

import pytest

from skeleton.shells.workspace_txn.state_machine import TransactionStateMachine
from skeleton.shells.workspace_txn.types import WorkspaceTransactionState


def test_all_states_are_covered_by_machine():
    machine = TransactionStateMachine()
    for state in WorkspaceTransactionState:
        assert isinstance(machine.allowed_targets(state), frozenset)



def test_transition_created_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_created_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_created_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_created_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_created_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_created_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_created_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_created_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_created_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_created_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_created_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_created_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.CREATED
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_leased_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_leased_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_leased_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_leased_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_leased_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_leased_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_leased_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_leased_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_leased_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_leased_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_leased_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_leased_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.LEASED
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_snapshotting_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_snapshotting_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_snapshotting_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_snapshotting_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_snapshotting_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_snapshotting_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_snapshotting_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_snapshotting_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_snapshotting_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_snapshotting_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_snapshotting_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_snapshotting_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.SNAPSHOTTING
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_backing_up_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_backing_up_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_backing_up_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_backing_up_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_backing_up_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_backing_up_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_backing_up_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_backing_up_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_backing_up_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_backing_up_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_backing_up_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_backing_up_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.BACKING_UP
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_executing_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_executing_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_executing_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_executing_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_executing_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_executing_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_executing_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_executing_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_executing_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_executing_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_executing_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_executing_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.EXECUTING
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_reviewing_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_reviewing_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_reviewing_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_reviewing_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_reviewing_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_reviewing_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_reviewing_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_reviewing_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_reviewing_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_reviewing_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_reviewing_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_reviewing_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REVIEWING
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_accepted_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_accepted_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ACCEPTED
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_rejected_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rejected_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.REJECTED
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_rolling_back_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolling_back_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolling_back_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolling_back_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolling_back_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolling_back_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolling_back_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolling_back_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolling_back_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolling_back_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_rolling_back_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_rolling_back_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLING_BACK
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is True
    assert decision.source is source
    assert decision.target is target
    machine.require(source, target)

def test_transition_rolled_back_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rolled_back_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLED_BACK
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_rollback_failed_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ROLLBACK_FAILED
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_created():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.CREATED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_leased():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.LEASED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_snapshotting():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.SNAPSHOTTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_backing_up():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.BACKING_UP
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_executing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.EXECUTING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_reviewing():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.REVIEWING
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_accepted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.ACCEPTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_rejected():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.REJECTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_rolling_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.ROLLING_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_rolled_back():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.ROLLED_BACK
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_rollback_failed():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.ROLLBACK_FAILED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)

def test_transition_aborted_to_aborted():
    machine = TransactionStateMachine()
    source = WorkspaceTransactionState.ABORTED
    target = WorkspaceTransactionState.ABORTED
    decision = machine.inspect(source, target)
    assert decision.allowed is False
    assert decision.source is source
    assert decision.target is target
    with pytest.raises(RuntimeError):
        machine.require(source, target)
