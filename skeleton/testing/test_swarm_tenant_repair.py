from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_runtime import SwarmTask, TaskState
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker
from skeleton.api.swarm_tenant_broker_routes import repair


def _tenant(runtime: HardenedSwarmRuntime) -> TenantSwarmBroker:
    return TenantSwarmBroker(SwarmBroker(runtime), SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))


def test_repair_removes_orphaned_active_accounting() -> None:
    runtime = HardenedSwarmRuntime(); broker = _tenant(runtime)
    broker.submit_and_dispatch("acme", SwarmTask("task", {})); broker.rebind(SwarmBroker(HardenedSwarmRuntime()))
    assert broker.reconcile()["missing_active"] == ("task",)
    result = broker.repair(); assert result.removed_orphans == 1
    assert broker.reconcile()["missing_active"] == (); assert broker.status()["ingress"]["accounted_tasks"] == 0


def test_repair_restores_missing_ingress_accounting() -> None:
    runtime = HardenedSwarmRuntime(); runtime.submit(SwarmTask("task", {"x": 1})); broker = _tenant(runtime)
    broker._tenant_by_task["task"] = "acme"
    assert broker.reconcile()["phase_mismatch"] == ("task",)
    result = broker.repair(); assert result.restored_accounting == 1
    assert broker.ingress.phase("acme", "task") == "queued"; assert broker.reconcile()["phase_mismatch"] == ()


def test_repair_moves_runtime_terminal_task_to_terminal_index() -> None:
    runtime = HardenedSwarmRuntime(); runtime.register_worker("w"); broker = _tenant(runtime)
    broker.submit_and_dispatch("acme", SwarmTask("task", {})); runtime.succeed("w", "task")
    assert broker.reconcile()["active_terminal"] == ("task",)
    result = broker.repair(); assert result.terminalized == 1
    assert broker.status()["tracked_tasks"] == 0; assert broker.status()["terminal_records"] == 1
    assert broker.ingress.phase("acme", "task") is None


def test_repair_fixes_leased_to_queued_phase_after_restore() -> None:
    runtime = HardenedSwarmRuntime(); runtime.register_worker("w"); broker = _tenant(runtime)
    broker.submit_and_dispatch("acme", SwarmTask("task", {}))
    restored = HardenedSwarmRuntime.from_state(runtime.export_state(), requeue_leased=True); broker.rebind(SwarmBroker(restored))
    assert restored.task("task").state is TaskState.QUEUED; assert broker.reconcile()["phase_mismatch"] == ("task",)
    result = broker.repair(); assert result.phase_repairs == 1; assert broker.ingress.phase("acme", "task") == "queued"


def test_repair_reactivated_terminal_record_fixes_existing_wrong_phase() -> None:
    runtime = HardenedSwarmRuntime(); runtime.register_worker("w"); broker = _tenant(runtime)
    broker.submit_and_dispatch("acme", SwarmTask("task", {})); broker.record_success("w", "task", completion_token="done")
    revived = HardenedSwarmRuntime(); revived.submit(SwarmTask("task", {}))
    broker.ingress.restore_task("acme", "task", {}, phase="leased"); broker.rebind(SwarmBroker(revived))
    assert broker.reconcile()["terminal_not_terminal"] == ("task",)
    result = broker.repair(); assert result.reactivated == 1; assert result.phase_repairs == 1
    assert broker.ingress.phase("acme", "task") == "queued"; assert all(not items for items in broker.reconcile().values())


def test_repair_api_returns_clean_reconciliation() -> None:
    runtime = HardenedSwarmRuntime(); broker = _tenant(runtime)
    broker.submit_and_dispatch("acme", SwarmTask("task", {})); broker.rebind(SwarmBroker(HardenedSwarmRuntime()))
    response = repair(broker=broker); assert response["repair"]["removed_orphans"] == 1
    assert all(not items for items in response["reconcile"].values())
