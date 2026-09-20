"""Assurance invariant helpers for Skeleton kernel.

Keeps assurance checks as small deterministic predicates that can be
registered with the existing InvariantLattice.
"""

from __future__ import annotations

from typing import Any, Dict


REQUIRED_FIELDS = ("task_id", "digest")


def has_identity(payload: Dict[str, Any]) -> bool:
    """Require an event/task identity before trusted processing."""
    value = payload.get("task_id")
    return isinstance(value, str) and bool(value.strip())


def has_digest(payload: Dict[str, Any]) -> bool:
    """Require provenance digest before accepted state handling."""
    value = payload.get("digest")
    return isinstance(value, str) and bool(value.strip())


def accepted_event_is_valid(payload: Dict[str, Any]) -> bool:
    """Accepted assurance events must carry identity and evidence."""
    return has_identity(payload) and has_digest(payload)


def rejected_event_blocks_mutation(payload: Dict[str, Any]) -> bool:
    """Rejected events must not be marked as mutation-safe."""
    return payload.get("state") != "REJECTED" or payload.get("mutation_allowed") is not True
