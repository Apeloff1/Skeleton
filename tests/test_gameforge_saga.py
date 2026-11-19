import pytest

from skeleton.frontier.gameforge_saga import Saga, SagaState


def test_saga_commit_then_compensation() -> None:
    saga = Saga()
    saga.commit()
    assert saga.state is SagaState.COMMITTED
    saga.compensate()
    saga.finish_compensation()
    assert saga.state is SagaState.COMPENSATED


def test_saga_rejects_invalid_transitions() -> None:
    saga = Saga()
    with pytest.raises(RuntimeError):
        saga.compensate()
    saga.commit()
    saga.compensate()
    with pytest.raises(RuntimeError):
        saga.commit()


def test_saga_terminal_compensation_is_stable() -> None:
    saga = Saga()
    saga.commit()
    saga.compensate()
    saga.finish_compensation()
    with pytest.raises(RuntimeError):
        saga.fail()
