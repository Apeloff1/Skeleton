from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_supervisor import SwarmSupervisor
from skeleton.api.server import ServerState


def test_bind_swarm_runtime_rebuilds_broker_and_preserves_supervisor() -> None:
    state = ServerState()
    supervisor = SwarmSupervisor()
    first = HardenedSwarmRuntime()
    state.swarm_supervisor = supervisor
    state.bind_swarm_runtime(first)
    first_broker = state.swarm_broker

    second = HardenedSwarmRuntime()
    state.bind_swarm_runtime(second)

    assert isinstance(state.swarm_broker, SwarmBroker)
    assert state.swarm is second
    assert state.swarm_broker.runtime is second
    assert state.swarm_broker is not first_broker
    assert state.swarm_broker.supervisor is supervisor


def test_bind_swarm_runtime_creates_supervisor_when_missing() -> None:
    state = ServerState()
    runtime = HardenedSwarmRuntime()
    state.bind_swarm_runtime(runtime)
    assert state.swarm_supervisor is not None
    assert state.swarm_broker.supervisor is state.swarm_supervisor
