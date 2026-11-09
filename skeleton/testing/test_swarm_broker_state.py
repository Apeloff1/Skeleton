from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_supervisor import SwarmSupervisor
from skeleton.api import swarm_broker_routes
from skeleton.api.server import get_state


def test_broker_dependency_rebinds_after_runtime_replacement() -> None:
    state = get_state()
    original_runtime = state.swarm
    original_broker = getattr(state, "swarm_broker", None)
    original_supervisor = getattr(state, "swarm_supervisor", None)
    try:
        supervisor = SwarmSupervisor()
        first = HardenedSwarmRuntime()
        state.swarm = first
        state.swarm_supervisor = supervisor
        state.swarm_broker = SwarmBroker(first, supervisor=supervisor)

        second = HardenedSwarmRuntime()
        state.swarm = second
        rebound = swarm_broker_routes._broker(runtime=second)

        assert rebound.runtime is second
        assert rebound.supervisor is supervisor
        assert state.swarm_broker is rebound
    finally:
        state.swarm = original_runtime
        state.swarm_broker = original_broker
        state.swarm_supervisor = original_supervisor


def test_supervisor_and_broker_share_same_instance() -> None:
    state = get_state()
    original_runtime = state.swarm
    original_broker = getattr(state, "swarm_broker", None)
    original_supervisor = getattr(state, "swarm_supervisor", None)
    try:
        runtime = HardenedSwarmRuntime()
        state.swarm = runtime
        state.swarm_supervisor = None
        state.swarm_broker = None
        broker = swarm_broker_routes._broker(runtime=runtime)
        assert state.swarm_supervisor is broker.supervisor
    finally:
        state.swarm = original_runtime
        state.swarm_broker = original_broker
        state.swarm_supervisor = original_supervisor
