"""Atomic activation of retained swarm recovery checkpoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker
from skeleton.agents.swarm_tenant_checkpoint import TenantCheckpointStore


@dataclass(frozen=True, slots=True)
class RecoveryActivation:
    sequence: int
    tenant_repair: dict[str, Any] | None
    tenant_source: str


def _stage_tenant_bundle(state: Any, runtime: Any, current: TenantSwarmBroker) -> tuple[Any, SwarmBroker, TenantSwarmBroker]:
    ingress = current.ingress.fork_empty()
    broker = SwarmBroker(runtime, supervisor=state.swarm_supervisor)
    tenant = TenantSwarmBroker(
        broker,
        ingress,
        max_terminal_records=current.max_terminal_records,
    )
    return ingress, broker, tenant


def activate_recovery(state: Any, recovery: SwarmRecoveryManager, sequence: int) -> RecoveryActivation:
    """Stage and atomically publish one retained checkpoint or raise before mutation."""
    runtime = recovery.restore(sequence)
    if runtime is None:
        raise KeyError(f"checkpoint not found: {sequence}")

    current = getattr(state, "swarm_tenant_broker", None)
    if current is None:
        state.bind_swarm_runtime(runtime)
        return RecoveryActivation(sequence, None, "none")

    # Hold the old execution generation through staging and publication. Requests already
    # running finish before this lock is acquired; requests waiting behind it wake only
    # after commit_swarm_bundle() retires this generation and therefore fail closed.
    with current._lock:
        current._assert_active()
        ingress, broker, tenant = _stage_tenant_bundle(state, runtime, current)
        sidecar = recovery.tenant_store.get(sequence)
        if sidecar is not None:
            repair = recovery.restore_tenants(tenant, sequence)
            if repair is None:
                raise RuntimeError(f"tenant checkpoint disappeared during activation: {sequence}")
            source = "checkpoint"
        else:
            transient = TenantCheckpointStore(max_checkpoints=1)
            transient.capture(1, current)
            repair = transient.restore(tenant, 1)
            source = "live"

        state.commit_swarm_bundle(runtime, broker, ingress, tenant)
        return RecoveryActivation(sequence, asdict(repair), source)
