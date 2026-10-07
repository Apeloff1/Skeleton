from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmTask
from skeleton.api.server import ServerState


def _state() -> ServerState:
    state = ServerState()
    state.bind_swarm_runtime(HardenedSwarmRuntime())
    state.bind_swarm_ingress(SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))
    state.swarm_recovery = SwarmRecoveryManager()
    return state


def test_health_is_ready_when_runtime_and_tenant_checkpoints_align() -> None:
    state = _state()
    state.swarm_recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    health = state.is_healthy()
    assert health["checks"]["swarm_recovery"]["tenant_aligned"] is True
    assert health["overall"] is True


def test_health_fails_when_tenant_checkpoint_lags_runtime() -> None:
    state = _state()
    state.swarm_recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    state.swarm.submit(SwarmTask("later", {}))
    state.swarm_recovery.checkpoint(state.swarm)

    health = state.is_healthy()

    assert health["checks"]["swarm_recovery"]["tenant_aligned"] is False
    assert health["overall"] is False


def test_runtime_only_history_without_any_sidecar_remains_ready() -> None:
    state = _state()
    state.swarm_recovery.checkpoint(state.swarm)
    health = state.is_healthy()
    assert health["checks"]["swarm_recovery"]["latest_tenant_sequence"] is None
    assert health["checks"]["swarm_recovery"]["tenant_aligned"] is True
    assert health["overall"] is True


def test_health_fails_when_tenant_phase_drifts_from_runtime() -> None:
    state = _state()
    state.swarm.register_worker("w")
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    task = state.swarm.task("task")
    assert task is not None and task.state.value == "leased"

    state.swarm_ingress.mark_requeued("acme", "task")
    health = state.is_healthy()

    assert health["checks"]["swarm_tenant_broker"]["reconcile"]["phase_mismatch"] == ("task",)
    assert health["overall"] is False


def test_health_fails_when_active_tenant_record_points_to_terminal_task() -> None:
    state = _state()
    state.swarm.register_worker("w")
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    state.swarm.succeed("w", "task")

    health = state.is_healthy()

    assert health["checks"]["swarm_tenant_broker"]["reconcile"]["active_terminal"] == ("task",)
    assert health["overall"] is False


def test_health_returns_ready_after_tenant_repair_clears_drift() -> None:
    state = _state()
    state.swarm.register_worker("w")
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    state.swarm.succeed("w", "task")
    assert state.is_healthy()["overall"] is False

    repair = state.swarm_tenant_broker.repair()
    health = state.is_healthy()

    assert repair.terminalized == 1
    assert health["checks"]["swarm_tenant_broker"]["reconcile"] == {
        "missing_active": (),
        "terminal_not_terminal": (),
        "active_terminal": (),
        "phase_mismatch": (),
    }
    assert health["overall"] is True
