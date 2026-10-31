"""Compatibility namespace for canonical automation Swarm runtime.

New code should import from :mod:`skeleton.automation.swarm`.

This package must not import the canonical package at module import time.
``skeleton.automation.swarm`` loads agent code that imports
``skeleton.swarm.handoff`` while the canonical package is still initialising.
An eager star-import here re-enters that package and raises ``ImportError``.
Names resolve on first use instead.
"""
from __future__ import annotations

from typing import Any

# Static export list so ``from skeleton.swarm import *`` works without
# importing the canonical package during this module's own initialisation.
__all__ = [
    "N_CAP",
    "PACKET",
    "VERSION",
    "Agent",
    "AgentHandoff",
    "ArbitrationCandidate",
    "ArbitrationDecision",
    "ArbitrationStatus",
    "BoundedOrchestrationPolicy",
    "CapabilityNegotiator",
    "ConflictDomain",
    "ConflictDomainBusy",
    "ConflictDomainRegistry",
    "ConflictRecord",
    "EvidenceArbitrator",
    "EvidenceClaim",
    "FencingToken",
    "HiveMind",
    "Mesh",
    "MultiAgentOrchestrationError",
    "MultiAgentOrchestrator",
    "PheromoneField",
    "Platoons",
    "ReadyWaveReport",
    "ReadyWaveRunner",
    "StigmergicRouter",
    "SubmitError",
    "SwarmDag",
    "SwarmMesh",
    "TaskNode",
    "TaskStatus",
    "WorkLease",
    "boundary",
    "capabilities",
    "handoff",
    "standard_platoons",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from skeleton.automation import swarm as canonical

    return getattr(canonical, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
