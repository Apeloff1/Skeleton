import pytest

from frontier.repair_state import RepairLifecycle, RepairState


def test_lifecycle_progresses_to_terminal_state():
    lifecycle = RepairLifecycle()
    lifecycle.transition(RepairState.RUNNING)
    lifecycle.transition(RepairState.COMPLETE)
    assert lifecycle.state is RepairState.COMPLETE
    with pytest.raises(ValueError):
        lifecycle.transition(RepairState.PENDING)


def test_blocked_work_can_be_requeued():
    lifecycle = RepairLifecycle()
    lifecycle.transition(RepairState.BLOCKED)
    lifecycle.transition(RepairState.PENDING)
    assert lifecycle.state is RepairState.PENDING
