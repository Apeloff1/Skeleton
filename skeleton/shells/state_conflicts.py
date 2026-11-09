"""Shared distributed-state conflicts for core shell infrastructure.

These exceptions live outside the AI package so low-level shell primitives can
depend on durable compare-and-swap semantics without importing the entire AI
control plane.  The AI distributed-state module re-exports the exact classes,
preserving exception identity for existing callers.
"""


class DistributedStateConflict(RuntimeError):
    """A versioned state mutation lost a compare-and-swap race."""


class LeaseConflict(RuntimeError):
    """A distributed lease or fencing-token operation is stale or invalid."""
