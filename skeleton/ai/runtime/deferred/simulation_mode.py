"""Fail-closed simulation execution for VOL-197.

Simulation is an execution mode, never promotion or production evidence.  The
runtime binds every invocation to an explicit simulated adapter, authority
grant, deterministic input/output digests, and bounded resource accounting.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .contracts import Budget, BudgetLedger, sha256_json


@dataclass(frozen=True, slots=True)
class SimulationAuthority:
    principal_id: str
    allowed_adapters: tuple[str, ...]
    max_cost_units: int
    max_latency_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.principal_id, str) or not self.principal_id.strip():
            raise ValueError("principal_id must be non-empty")
        if not self.allowed_adapters or any(
            not isinstance(item, str) or not item.strip() for item in self.allowed_adapters
        ):
            raise ValueError("allowed_adapters must be non-empty text")
        if len(self.allowed_adapters) != len(set(self.allowed_adapters)):
            raise ValueError("allowed_adapters must be unique")
        for name in ("max_cost_units", "max_latency_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be positive integer")


@dataclass(frozen=True, slots=True)
class SimulationRequest:
    operation_id: str
    adapter_id: str
    arguments: Mapping[str, Any]
    cost_units: int = 1
    latency_ms: int = 1

    def __post_init__(self) -> None:
        for name in ("operation_id", "adapter_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not isinstance(self.arguments, Mapping):
            raise TypeError("arguments must be a mapping")
        for name in ("cost_units", "latency_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative integer")

    @property
    def input_digest(self) -> str:
        return sha256_json(
            {
                "operation_id": self.operation_id,
                "adapter_id": self.adapter_id,
                "arguments": dict(self.arguments),
            }
        )


@dataclass(frozen=True, slots=True)
class SimulationEvidence:
    operation_id: str
    adapter_id: str
    principal_id: str
    input_digest: str
    output_digest: str
    simulated: bool = True
    production_eligible: bool = False

    def __post_init__(self) -> None:
        if self.simulated is not True:
            raise ValueError("simulation evidence must be marked simulated")
        if self.production_eligible is not False:
            raise ValueError("simulation evidence can never be production eligible")

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "operation_id": self.operation_id,
                "adapter_id": self.adapter_id,
                "principal_id": self.principal_id,
                "input_digest": self.input_digest,
                "output_digest": self.output_digest,
                "simulated": True,
                "production_eligible": False,
            }
        )


@dataclass(frozen=True, slots=True)
class SimulationResult:
    output: Any
    evidence: SimulationEvidence


class SimulationRuntime:
    """Executes only registered simulated adapters under explicit authority."""

    def __init__(self) -> None:
        self._adapters: dict[str, Callable[[Mapping[str, Any]], Any]] = {}
        self._replay: dict[str, SimulationResult] = {}

    def register(
        self,
        adapter_id: str,
        handler: Callable[[Mapping[str, Any]], Any],
        *,
        simulated: bool,
    ) -> None:
        if simulated is not True:
            raise PermissionError("production adapter cannot enter simulation runtime")
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise ValueError("adapter_id must be non-empty")
        if not callable(handler):
            raise TypeError("handler must be callable")
        if adapter_id in self._adapters:
            raise ValueError("adapter already registered")
        self._adapters[adapter_id] = handler

    def execute(
        self,
        request: SimulationRequest,
        authority: SimulationAuthority,
    ) -> SimulationResult:
        if request.adapter_id not in authority.allowed_adapters:
            raise PermissionError("adapter is outside simulation authority")
        handler = self._adapters.get(request.adapter_id)
        if handler is None:
            raise PermissionError("unregistered adapter fails closed")

        prior = self._replay.get(request.operation_id)
        if prior is not None:
            if prior.evidence.input_digest != request.input_digest:
                raise ValueError("operation replay input collision")
            return prior

        ledger = BudgetLedger(
            Budget(
                max_attempts=1,
                max_cost_units=authority.max_cost_units,
                max_latency_ms=authority.max_latency_ms,
            )
        )
        ledger.admit(cost_units=request.cost_units, latency_ms=request.latency_ms)
        output = handler(dict(request.arguments))
        output_digest = sha256_json(output)
        evidence = SimulationEvidence(
            operation_id=request.operation_id,
            adapter_id=request.adapter_id,
            principal_id=authority.principal_id,
            input_digest=request.input_digest,
            output_digest=output_digest,
        )
        result = SimulationResult(output=output, evidence=evidence)
        self._replay[request.operation_id] = result
        return result

    def replay(self, operation_id: str) -> SimulationResult:
        try:
            return self._replay[operation_id]
        except KeyError as exc:
            raise KeyError("unknown simulation operation") from exc
