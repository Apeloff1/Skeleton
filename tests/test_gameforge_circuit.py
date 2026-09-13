from skeleton.frontier.gameforge_circuit import Circuit,CircuitState

def test_circuit_opens_after_threshold_and_probes():
 c=Circuit(2); c.failure(); assert c.state is CircuitState.CLOSED; c.failure(); assert c.state is CircuitState.OPEN; assert c.probe(); assert c.state is CircuitState.HALF_OPEN; c.success(); assert c.state is CircuitState.CLOSED
