"""Aggregate shell-plane status snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.shells.circuit import CircuitRegistry
from skeleton.shells.health import inspect_policy
from skeleton.shells.receipts import ReceiptChain
from skeleton.shells.runner import ShellRunner
from skeleton.shells.telemetry import ShellTelemetry


@dataclass(frozen=True)
class ShellPlaneStatus:
    healthy: bool
    policy_health: dict[str, Any]
    metrics: dict[str, dict[str, int | float]]
    circuits: dict[str, str]
    receipt_chain_valid: bool | None
    receipt_root: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "policy_health": self.policy_health,
            "metrics": self.metrics,
            "circuits": self.circuits,
            "receipt_chain_valid": self.receipt_chain_valid,
            "receipt_root": self.receipt_root,
        }


def status_snapshot(
    runner: ShellRunner,
    telemetry: ShellTelemetry,
    circuits: CircuitRegistry,
    receipts: ReceiptChain | None = None,
) -> ShellPlaneStatus:
    health = inspect_policy(runner.policy)
    metrics = {command: metric.to_dict() for command, metric in telemetry.snapshot().items()}
    circuit_states = {key: snapshot.state.value for key, snapshot in circuits.snapshot().items()}
    receipt_valid = None if receipts is None else receipts.verify()
    receipt_root = None if receipts is None else receipts.root_hash()
    healthy = health.healthy and all(state != "open" for state in circuit_states.values())
    if receipt_valid is False:
        healthy = False
    return ShellPlaneStatus(
        healthy,
        health.to_dict(),
        metrics,
        circuit_states,
        receipt_valid,
        receipt_root,
    )
