"""B082: deny-by-default capability + quota policy for generated code.

Enforcement already lives in :mod:`skeleton.sandbox`; this module is the
deterministic, auditable policy decision that feeds the release gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ._core import ContractError, require, verdict

KINDS = ("fs_read", "fs_write", "network", "process")


@dataclass(frozen=True)
class Quota:
    cpu_ms: int
    memory_mb: int
    wall_ms: int

    def __post_init__(self) -> None:
        for name in ("cpu_ms", "memory_mb", "wall_ms"):
            v = getattr(self, name)
            require(isinstance(v, int) and v > 0, f"quota {name} must be positive int")


@dataclass(frozen=True)
class SandboxPolicy:
    grants: Mapping[str, tuple[str, ...]]
    quota: Quota

    def __post_init__(self) -> None:
        for k in self.grants:
            require(k in KINDS, f"unknown capability {k}")

    def decide(self, kind: str, target: str) -> bool:
        if kind not in KINDS:
            raise ContractError(f"unknown capability {kind}")
        allowed = self.grants.get(kind, ())
        if kind == "network":
            return target in allowed
        return any(target == p or target.startswith(p.rstrip("/") + "/") for p in allowed)

    def within_quota(self, cpu_ms: int, memory_mb: int, wall_ms: int) -> bool:
        q = self.quota
        return cpu_ms <= q.cpu_ms and memory_mb <= q.memory_mb and wall_ms <= q.wall_ms


def evaluate(policy: SandboxPolicy, probes: list[tuple[str, str]]):
    """Probes are effects that MUST be denied; any allowed probe is a finding."""
    findings = [f"leak:{k}:{t}" for k, t in probes if policy.decide(k, t)]
    if policy.grants.get("process"):
        findings.append("process_spawn_granted")
    return verdict("B082", findings, probes=len(probes))
