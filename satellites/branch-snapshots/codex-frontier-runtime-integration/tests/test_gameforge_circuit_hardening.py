from skeleton.frontier.gameforge_circuit import Circuit, CircuitState


def test_circuit_opens_and_probes():
    circuit = Circuit(2)
    assert circuit.failure() is CircuitState.CLOSED
    assert circuit.failure() is CircuitState.OPEN
    assert circuit.open
    assert not circuit.allowed
    assert circuit.probe()
    assert circuit.state is CircuitState.HALF_OPEN
    circuit.success()
    assert circuit.state is CircuitState.CLOSED
    assert circuit.allowed
    assert circuit.failures == 0
