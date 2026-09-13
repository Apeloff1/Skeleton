from skeleton.frontier.gameforge_circuit import Circuit,CircuitState

def test_circuit_opens_after_threshold_and_probes():
 c=Circuit(2); assert c.allowed; c.failure(); assert c.state is CircuitState.CLOSED; c.failure(); assert not c.allowed; assert c.probe(); assert c.state is CircuitState.HALF_OPEN; c.success(); assert c.allowed; assert c.state is CircuitState.CLOSED
