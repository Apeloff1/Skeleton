"""Small saga state contract distilled from gameforge-rs service architecture."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SagaState(str, Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


@dataclass
class Saga:
    """Fail-safe state machine: terminal states cannot be advanced."""

    state: SagaState = SagaState.PENDING

    def commit(self) -> None:
        if self.state is not SagaState.PENDING:
            raise RuntimeError("only pending sagas may commit")
        self.state = SagaState.COMMITTED

    def compensate(self) -> None:
        if self.state is not SagaState.COMMITTED:
            raise RuntimeError("only committed sagas may compensate")
        self.state = SagaState.COMPENSATING

    def finish_compensation(self) -> None:
        if self.state is not SagaState.COMPENSATING:
            raise RuntimeError("compensation is not active")
        self.state = SagaState.COMPENSATED

    def fail(self) -> None:
        if self.state in {SagaState.COMPENSATED, SagaState.FAILED}:
            raise RuntimeError("terminal saga cannot fail again")
        self.state = SagaState.FAILED
