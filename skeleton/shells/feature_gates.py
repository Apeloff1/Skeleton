"""Deterministic feature gates for shell-plane capability rollout."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import threading
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class FeatureGate:
    name: str
    enabled: bool = False
    rollout_percent: int = 0
    allow_principals: frozenset[str] = frozenset()
    deny_principals: frozenset[str] = frozenset()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 128:
            raise ValueError("invalid feature gate name")
        if not isinstance(self.rollout_percent, int) or isinstance(self.rollout_percent, bool):
            raise ValueError("rollout_percent must be an integer")
        if not 0 <= self.rollout_percent <= 100:
            raise ValueError("rollout_percent must be between 0 and 100")
        if self.allow_principals & self.deny_principals:
            raise ValueError("principal cannot be both allowed and denied")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many gate metadata fields")
        if any(
            not isinstance(k, str) or not isinstance(v, str) or len(k) > 128 or len(v) > 512
            for k, v in metadata.items()
        ):
            raise ValueError("invalid feature gate metadata")
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def evaluate(self, principal: str) -> bool:
        if not principal or len(principal) > 256:
            raise ValueError("invalid principal")
        if principal in self.deny_principals:
            return False
        if principal in self.allow_principals:
            return True
        if not self.enabled:
            return False
        if self.rollout_percent >= 100:
            return True
        if self.rollout_percent <= 0:
            return False
        bucket = int(hashlib.sha256(f"{self.name}:{principal}".encode()).hexdigest()[:8], 16) % 100
        return bucket < self.rollout_percent


class FeatureGateRegistry:
    def __init__(self, *, max_gates: int = 1000) -> None:
        if max_gates <= 0:
            raise ValueError("max_gates must be positive")
        self.max_gates = max_gates
        self._gates: dict[str, FeatureGate] = {}
        self._lock = threading.RLock()

    def set(self, gate: FeatureGate) -> None:
        if not isinstance(gate, FeatureGate):
            raise TypeError("gate must be FeatureGate")
        with self._lock:
            if gate.name not in self._gates and len(self._gates) >= self.max_gates:
                raise RuntimeError("feature gate capacity exhausted")
            self._gates[gate.name] = gate

    def get(self, name: str) -> FeatureGate:
        with self._lock:
            return self._gates[name]

    def enabled(self, name: str, principal: str) -> bool:
        with self._lock:
            gate = self._gates.get(name)
            return False if gate is None else gate.evaluate(principal)

    def remove(self, name: str) -> bool:
        with self._lock:
            return self._gates.pop(name, None) is not None

    def snapshot(self) -> tuple[FeatureGate, ...]:
        with self._lock:
            return tuple(self._gates[key] for key in sorted(self._gates))
