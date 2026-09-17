"""Stable capability discovery for Skeleton's canonical subsystems.

The manifest is intentionally curated rather than derived from the filesystem.
That makes it safe for CLI/API consumers to depend on stable capability IDs even
as internal modules move or experimental packages come and go.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Final, Mapping


CAPABILITY_MANIFEST_VERSION: Final = 1


@dataclass(frozen=True, slots=True)
class Capability:
    """One stable, discoverable Skeleton capability."""

    id: str
    module: str
    description: str


CAPABILITIES: Final[tuple[Capability, ...]] = (
    Capability(
        id="application",
        module="skeleton.application",
        description="Shared command contracts and runtime command orchestration.",
    ),
    Capability(
        id="gameforge",
        module="skeleton.forge",
        description="Blueprint compilation, validation, simulation, and project materialisation.",
    ),
    Capability(
        id="cortex",
        module="skeleton.cortex",
        description="Owned model, learning, routing, interchange, and inference primitives.",
    ),
    Capability(
        id="jeeves",
        module="skeleton.jeeves",
        description="GameForge tutor brain, planning, pedagogy, and LLM orchestration.",
    ),
    Capability(
        id="organism",
        module="skeleton.organism",
        description="Runtime state, feature flags, health, quality, and operator control plane.",
    ),
    Capability(
        id="social",
        module="skeleton.social",
        description="Agent relationships, reputation, and interaction history.",
    ),
    Capability(
        id="galaxy",
        module="skeleton.galaxy",
        description="Federation, transport, consensus, synchronization, and fleet coordination.",
    ),
    Capability(
        id="kernel",
        module="skeleton.kernel",
        description="Core primitives, events, identity, and fail-closed error types.",
    ),
    Capability(
        id="memory",
        module="skeleton.memory",
        description="Multi-plane storage, fusion, drift detection, and spaced consolidation.",
    ),
    Capability(
        id="intelligence",
        module="skeleton.intelligence",
        description="Reasoning orchestration, adaptive learning, and meta-grid control.",
    ),
    Capability(
        id="swarm",
        module="skeleton.swarm",
        description="Multi-agent routing, stigmergy, consensus, and platoon coordination.",
    ),
    Capability(
        id="resilience",
        module="skeleton.resilience",
        description="Input sanitization, threat detection, and canary rollout control.",
    ),
    Capability(
        id="observability",
        module="skeleton.observability",
        description="Metrics, sampling, anomaly detection, and operator diagnostics.",
    ),
    Capability(
        id="api",
        module="skeleton.api",
        description="REST transport, HMAC seals, and shared command dispatch.",
    ),
    Capability(
        id="developer",
        module="skeleton.developer",
        description="Scaffolding, wizard, health dashboard, and extension generation.",
    ),
    Capability(
        id="deploy",
        module="skeleton.deploy",
        description="Deployment harness and environment configuration.",
    ),
    Capability(
        id="testing",
        module="skeleton.testing",
        description="In-tree test framework, scaffolds, and contract runners.",
    ),
    Capability(
        id="pipelines",
        module="skeleton.pipelines",
        description="NPC, game-logic, and animation generation pipelines.",
    ),
    Capability(
        id="vault",
        module="skeleton.vault",
        description="Access control, envelope encryption, and capability grants.",
    ),
    Capability(
        id="retrieval",
        module="skeleton.retrieval",
        description="Quad-plane search, fusion, ranking, and speculative prefetch.",
    ),
    Capability(
        id="agents",
        module="skeleton.agents",
        description="Agent pools, task assignment, and coordination.",
    ),
    Capability(
        id="context",
        module="skeleton.context",
        description="Intake questionnaires, cockpit control, and context tensors.",
    ),
    Capability(
        id="config",
        module="skeleton.config",
        description="Layered non-secret configuration snapshots.",
    ),
    Capability(
        id="content",
        module="skeleton.content",
        description="Reusable domain knowledge packs and adapters.",
    ),
)

CAPABILITIES_BY_ID: Final[Mapping[str, Capability]] = MappingProxyType(
    {capability.id: capability for capability in CAPABILITIES}
)


def get_capability(capability_id: str) -> Capability:
    """Return one capability by stable ID without exposing a mutable registry."""

    if not isinstance(capability_id, str):
        raise TypeError("capability_id must be a string")
    normalized = capability_id.strip().lower()
    if not normalized:
        raise ValueError("capability_id must not be empty")
    try:
        return CAPABILITIES_BY_ID[normalized]
    except KeyError as exc:
        raise KeyError(f"unknown capability: {normalized}") from exc


def capability_manifest() -> dict[str, object]:
    """Return the versioned, JSON-serializable capability manifest."""

    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "capabilities": [asdict(capability) for capability in CAPABILITIES],
    }
