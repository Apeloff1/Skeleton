"""
Skeleton Kernel — Registry module (canonical home)
"""

from __future__ import annotations

from skeleton.kernel.primitives import CapabilityRegistry

__all__ = ["CapabilityRegistry"]


class CapabilityKind:
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


def bootstrap_registry() -> CapabilityRegistry:
    """Create the canonical subsystem capability registry."""
    return CapabilityRegistry()
