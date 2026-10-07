from skeleton.frontier.gameforge_circuit import Circuit, CircuitState


def test_circuit_opens_probes_and_reopens_on_half_open_failure():
    circuit = Circuit(2)
    circuit.failure()
    circuit.failure()
    assert not circuit.allowed
    assert circuit.probe()
    assert circuit.state is CircuitState.HALF_OPEN
    assert not circuit.probe()
    circuit.failure()
    assert circuit.state is CircuitState.OPEN


def test_circuit_success_recovers():
    circuit = Circuit(1)
    circuit.failure()
    assert circuit.probe()
    circuit.success()
    assert circuit.allowed
    assert circuit.state is CircuitState.CLOSED
