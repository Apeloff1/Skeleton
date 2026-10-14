"""Compile year-aware runtime signals into deterministic serving policy receipts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .runtime_signals import RuntimeSignalRegistry, SignalMaturity, DEFAULT_RUNTIME_SIGNALS


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    through_year: int
    capabilities: tuple[str, ...]
    experimental: tuple[str, ...]
    digest: str

    def allows(self, capability: str) -> bool:
        return capability in self.capabilities or capability in self.experimental


class RuntimePolicyCompiler:
    """Fail-closed compiler from temporal signals to executable capability policy."""

    def __init__(self, registry: RuntimeSignalRegistry = DEFAULT_RUNTIME_SIGNALS) -> None:
        self.registry = registry

    def compile(
        self,
        through_year: int,
        *,
        requested: tuple[str, ...] = (),
        enable_experimental: tuple[str, ...] = (),
    ) -> RuntimePolicy:
        if isinstance(through_year, bool) or not isinstance(through_year, int):
            raise ValueError("integer policy year required")
        if len(requested) != len(set(requested)):
            raise ValueError("duplicate requested capability")
        if len(enable_experimental) != len(set(enable_experimental)):
            raise ValueError("duplicate experimental capability")

        signals = self.registry.through_year(through_year)
        by_capability = {signal.capability: signal for signal in signals}
        defaults = set(self.registry.production_policy(through_year))

        for capability in requested:
            signal = by_capability.get(capability)
            if signal is None:
                raise ValueError(f"capability unavailable through {through_year}: {capability}")
            if signal.maturity in {SignalMaturity.EMERGING, SignalMaturity.EXPERIMENTAL}:
                if capability not in enable_experimental:
                    raise ValueError(f"capability requires explicit experimental enablement: {capability}")
            defaults.add(capability)

        experimental: set[str] = set()
        for capability in enable_experimental:
            signal = by_capability.get(capability)
            if signal is None:
                raise ValueError(f"experimental capability unavailable through {through_year}: {capability}")
            if signal.maturity not in {SignalMaturity.EMERGING, SignalMaturity.EXPERIMENTAL}:
                raise ValueError(f"capability is not experimental: {capability}")
            if capability not in requested:
                raise ValueError(f"experimental enablement was not requested: {capability}")
            defaults.discard(capability)
            experimental.add(capability)

        capabilities = tuple(sorted(defaults))
        experimental_tuple = tuple(sorted(experimental))
        body = {
            "schema": "skeleton.ai.runtime-policy.v1",
            "through_year": through_year,
            "capabilities": capabilities,
            "experimental": experimental_tuple,
            "signal_digest": self.registry.snapshot(through_year)["digest"],
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return RuntimePolicy(through_year, capabilities, experimental_tuple, digest)


DEFAULT_RUNTIME_POLICY_COMPILER = RuntimePolicyCompiler()

__all__ = [
    "DEFAULT_RUNTIME_POLICY_COMPILER",
    "RuntimePolicy",
    "RuntimePolicyCompiler",
]
