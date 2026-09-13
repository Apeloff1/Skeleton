"""Explicit lifecycle for repair execution."""

from enum import Enum


class RepairState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    BLOCKED = "blocked"


class RepairLifecycle:
    _ALLOWED = {
        RepairState.PENDING: {RepairState.RUNNING, RepairState.BLOCKED},
        RepairState.RUNNING: {RepairState.COMPLETE, RepairState.BLOCKED},
        RepairState.BLOCKED: {RepairState.PENDING},
        RepairState.COMPLETE: set(),
    }

    def __init__(self) -> None:
        self._state = RepairState.PENDING

    @property
    def state(self) -> RepairState:
        return self._state

    def transition(self, state: RepairState) -> None:
        if not isinstance(state, RepairState):
            raise TypeError("state must be RepairState")
        if state not in self._ALLOWED[self._state]:
            raise ValueError(f"invalid transition: {self._state} -> {state}")
        self._state = state
