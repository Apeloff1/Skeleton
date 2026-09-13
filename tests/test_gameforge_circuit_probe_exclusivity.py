from skeleton.frontier.gameforge_circuit import Circuit, CircuitState


def test_half_open_allows_only_one_probe():
    circuit = Circuit(threshold=1)
    circuit.failure()
    assert circuit.state is CircuitState.OPEN
    assert circuit.probe() is True
    assert circuit.probe() is False
    assert circuit.allowed is True
    circuit.success()
    assert circuit.allowed is True
