"""Serialized local saga state machine; durable compensation requires a journal."""
from enum import Enum
from threading import Lock


class SagaState(str, Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


class Saga:
    def __init__(self, state: SagaState = SagaState.PENDING):
        if type(state) is not SagaState:
            raise ValueError("canonical saga state required")
        self._state = state
        self._lock = Lock()

    @property
    def state(self):
        with self._lock:
            return self._state

    def _transition(self, expected, target):
        with self._lock:
            if self._state not in expected:
                raise RuntimeError("invalid saga transition")
            self._state = target

    def commit(self):
        self._transition({SagaState.PENDING}, SagaState.COMMITTED)

    def compensate(self):
        self._transition({SagaState.COMMITTED}, SagaState.COMPENSATING)

    def finish_compensation(self):
        self._transition({SagaState.COMPENSATING}, SagaState.COMPENSATED)

    def fail(self):
        self._transition(
            {SagaState.PENDING, SagaState.COMMITTED, SagaState.COMPENSATING},
            SagaState.FAILED,
        )
