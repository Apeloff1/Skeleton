import pytest

from skeleton.frontier.gameforge_circuit import Circuit, CircuitState


def test_circuit_rejects_boolean_threshold():
    with pytest.raises(ValueError):
        Circuit(True)


def test_circuit_opens_at_threshold():
    circuit = Circuit(2)
    assert circuit.failure() is CircuitState.CLOSED
    assert circuit.failure() is CircuitState.OPEN
