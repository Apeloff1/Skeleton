"""
Skeleton Kernel — Events module (canonical home)

Re-exports event primitives from kernel.primitives so that
`skeleton.kernel.events` is a stable import path.
"""

from __future__ import annotations

from skeleton.kernel.primitives import DomainEvent, EventBus

__all__ = ["DomainEvent", "EventBus"]
