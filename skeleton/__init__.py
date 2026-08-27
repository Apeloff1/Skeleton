"""Tutolage Skeleton — the v16 rewrite of the Tutolage platform.

Root exports the kernel primitives plus the dependency-light first-class
subsystems; heavier surfaces (api routers, pipelines) stay in their own
packages to keep root imports cheap.
"""

__version__ = "16.0.0"
__codename__ = "Skeleton"

from skeleton.kernel.errors import SkeletonError
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.registry import CapabilityRegistry

# curated light exports from the new subsystems
from skeleton.config.snapshots import SettingsSnapshotBridge
from skeleton.retrieval.fusion import Fuser, FusionStrategy, ScoredResult
from skeleton.retrieval.ranking import Ranker
from skeleton.vault.access import AccessPolicy, Role
from skeleton.vault.kms import EnvelopeKMS
from skeleton.agents.coordination import Coordinator
from skeleton.observability.sampling import Sampler, default_sampler

__all__ = [
    "__version__",
    "__codename__",
    "SkeletonError",
    "EventBus",
    "DomainEvent",
    "CapabilityRegistry",
    "SettingsSnapshotBridge",
    "Fuser",
    "FusionStrategy",
    "ScoredResult",
    "Ranker",
    "AccessPolicy",
    "Role",
    "EnvelopeKMS",
    "Coordinator",
    "Sampler",
    "default_sampler",
]
