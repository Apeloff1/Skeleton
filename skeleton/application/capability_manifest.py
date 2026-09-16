"""Stable capability discovery for Skeleton's canonical subsystems.

The manifest is intentionally curated rather than derived from the filesystem.
That makes it safe for CLI/API consumers to depend on stable capability IDs even
as internal modules move or experimental packages come and go.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


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
)


def capability_manifest() -> dict[str, object]:
    """Return the versioned, JSON-serializable capability manifest."""

    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "capabilities": [asdict(capability) for capability in CAPABILITIES],
    }
