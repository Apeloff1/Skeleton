"""Tutolage Skeleton — the v16 rewrite of the Tutolage platform.

A rigorously layered, hexagonal codebase: kernel (pure domain), agents
(substrate), pipelines (Text-to-X generation), jeeves (AI tutor), forge
(system synthesis), api (HTTP interface).
"""

__version__ = "16.0.0"
__codename__ = "Skeleton"

from skeleton.kernel.errors import SkeletonError
from skeleton.kernel.events import EventBus, DomainEvent
from skeleton.kernel.registry import CapabilityRegistry

__all__ = [
    "__version__",
    "__codename__",
    "SkeletonError",
    "EventBus",
    "DomainEvent",
    "CapabilityRegistry",
]
