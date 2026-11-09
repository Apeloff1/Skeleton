import pytest
from fastapi import HTTPException

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.api import swarm_operator_routes as routes
from skeleton.api.server import ServerState


def _succeed(runtime: HardenedSwarmRuntime, task_id: str) -> None:
    if runtime.worker("w") is None:
        runtime.register_worker("w", capacity=10)
    runtime.submit(SwarmTask(task_id, {}))
    runtime.lease("w", limit=1)
    runtime.succeed("w", task_id)


def _state() -> ServerState:
    state = ServerState()
    state.bind_swarm_runtime(HardenedSwarmRuntime(max_tasks=20))
    state.bind_swarm_ingress(SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))
    return state


def test_prune_terminal_endpoint_reclaims_capacity() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=3)
    for task_id in ("one", "two", "three"):
        _succeed(runtime, task_id)

    result = routes.prune_terminal_tasks(keep_terminal=1, runtime=runtime)

    assert result["removed"] == 2
    assert result["planned"] == 2
    assert result["retained_terminal"] == 1
    assert result["capacity_after"]["resident"] == 1
    assert tuple(task.id for task in runtime.tasks()) == ("three",)


def test_prune_terminal_endpoint_is_idempotent() -> None:
    runtime = HardenedSwarmRuntime()
    _succeed(runtime, "done")
    first = routes.prune_terminal_tasks(keep_terminal=0, runtime=runtime)
    second = routes.prune_terminal_tasks(keep_terminal=0, runtime=runtime)
    assert first["removed"] == 1
    assert second["removed"] == 0


def test_prune_terminal_endpoint_rejects_runtime_without_forget_seam() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("queued", {}))
    # No terminal task means no forget call and is safely a no-op.
    assert routes.prune_terminal_tasks(keep_terminal=0, runtime=runtime)["removed"] == 0

    runtime.register_worker("w")
    runtime.lease("w")
    runtime.succeed("w", "queued")
    with pytest.raises(HTTPException) as exc:
        routes.prune_terminal_tasks(keep_terminal=0, runtime=runtime)
    assert exc.value.status_code == 409


def test_gc_swaps_tenant_bundle_atomically_and_preserves_active_accounting(monkeypatch) -> None:
    state = _state()
    state.swarm.register_worker("w", capacity=1)
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("done", {}))
    state.swarm_tenant_broker.record_success("w", "done", completion_token="done-token")
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("active", {"x": 1}))
    monkeypatch.setattr(routes, "_state", lambda: state)

    old_runtime = state.swarm
    old_tenant = state.swarm_tenant_broker
    result = routes.gc(keep_terminal=0, runtime=state.swarm)

    assert result["result"]["removed_terminal"] == 1
    assert state.swarm is not old_runtime
    assert state.swarm_tenant_broker is not old_tenant
    assert state.swarm.task("done") is None
    assert state.swarm_tenant_broker.tenant_for("done") == "acme"
    assert state.swarm_tenant_broker.tenant_for("active") == "acme"
    assert state.swarm_ingress.status()["accounted_tasks"] == 1
    assert state.swarm_broker.runtime is state.swarm


def test_gc_staging_failure_leaves_original_bundle_untouched(monkeypatch) -> None:
    state = _state()
    state.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("active", {}))
    monkeypatch.setattr(routes, "_state", lambda: state)

    old_runtime = state.swarm
    old_broker = state.swarm_broker
    old_ingress = state.swarm_ingress
    old_tenant = state.swarm_tenant_broker

    def reject(_runtime):
        raise ValueError("synthetic compaction conflict")

    monkeypatch.setattr(routes, "_publish_runtime", reject)
    with pytest.raises(HTTPException) as exc:
        routes.gc(keep_terminal=0, runtime=state.swarm)

    assert exc.value.status_code == 409
    assert state.swarm is old_runtime
    assert state.swarm_broker is old_broker
    assert state.swarm_ingress is old_ingress
    assert state.swarm_tenant_broker is old_tenant
    assert state.swarm_tenant_broker.tenant_for("active") == "acme"
