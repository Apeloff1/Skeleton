"""Analysis-chain execution planner with explicit worker capabilities.

Plans ready work from accepted evidence receipts, rather than inventing
completion. Missing worker implementations remain blocked. Rejected stages
cannot unlock descendants.
"""
from __future__ import annotations
from dataclasses import dataclass

from .dragon_analysis_chains import (
    AnalysisLayer, LayerReceipt, LayerSpec, DEFAULT_CHAIN, validate_chain,
)


@dataclass(frozen=True)
class WorkerCapability:
    layer: AnalysisLayer
    implementation: str
    version: str
    executable: bool


@dataclass(frozen=True)
class LayerDispatch:
    layer: AnalysisLayer
    input_fingerprints: tuple[str, ...]
    worker: str
    worker_version: str


@dataclass(frozen=True)
class ExecutionPlan:
    ready: tuple[LayerDispatch, ...]
    blocked: tuple[tuple[AnalysisLayer, str], ...]
    completed: tuple[AnalysisLayer, ...]


def plan_analysis_execution(
    receipts: tuple[LayerReceipt, ...],
    capabilities: tuple[WorkerCapability, ...], *,
    authorized: bool, chain: tuple[LayerSpec, ...] = DEFAULT_CHAIN,
    max_dispatch: int = 12,
) -> ExecutionPlan:
    if not authorized:
        raise PermissionError("analysis planning requires authorization")
    if not 1 <= max_dispatch <= 1000:
        raise ValueError("invalid dispatch budget")
    verdict = validate_chain(receipts, authorized=True, chain=chain)
    registered = {}
    for capability in capabilities:
        if capability.layer in registered:
            raise ValueError("duplicate worker capability")
        if not isinstance(capability.executable, bool):
            raise ValueError("invalid executable flag")
        if not isinstance(capability.implementation, str) or not 1 <= len(capability.implementation) <= 256:
            raise ValueError("invalid worker implementation")
        if not isinstance(capability.version, str) or not 1 <= len(capability.version) <= 128:
            raise ValueError("invalid worker version")
        registered[capability.layer] = capability
    receipt_by_layer = {r.layer: r for r in receipts}
    accepted = set(verdict.accepted_layers)
    rejected = set(verdict.rejected_layers)
    ready, blocked = [], []
    for spec in chain:
        layer = spec.layer
        if layer in accepted:
            continue
        if layer in rejected:
            blocked.append((layer, "submitted evidence failed validation"))
            continue
        missing = [dep for dep in spec.dependencies if dep not in accepted]
        if missing:
            blocked.append((layer, "prerequisite evidence missing or rejected"))
            continue
        capability = registered.get(layer)
        if capability is None or not capability.executable:
            blocked.append((layer, "no executable worker registered"))
            continue
        if len(ready) >= max_dispatch:
            blocked.append((layer, "dispatch budget exhausted"))
            continue
        ready.append(LayerDispatch(
            layer,
            tuple(receipt_by_layer[dep].output_fingerprint for dep in spec.dependencies),
            capability.implementation,
            capability.version,
        ))
    return ExecutionPlan(
        tuple(ready), tuple(blocked), verdict.accepted_layers,
    )
