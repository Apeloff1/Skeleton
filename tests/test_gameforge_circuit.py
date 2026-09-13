from skeleton.frontier.gameforge_circuit import Circuit,CircuitState

def test_circuit_opens_probes_and_reopens_on_half_open_failure():
 c=Circuit(2); c.failure(); c.failure(); assert not c.allowed; assert c.probe(); assert c.state is CircuitState.HALF_OPEN; c.failure(); assert c.state is CircuitState.OPEN

def test_circuit_success_recovers():
 c=Circuit(1); c.failure(); c.probe(); c.success(); assert c.allowed and c.state is CircuitState.CLOSED
