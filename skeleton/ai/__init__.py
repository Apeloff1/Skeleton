"""Canonical AI assembly namespace.

During migration, legacy source paths remain compatibility mirrors. The
machine/ai_file_tree.json contract governs cutover and drift.
"""

from skeleton.ai.capability_map import (
    CAPABILITY_MAP_SCHEMA,
    Availability,
    CapabilityAvailability,
    CapabilityDescriptor,
    CapabilityError,
    CapabilityEvidence,
    CapabilityMap,
    CapabilitySnapshot,
    Maturity,
)

__all__ = [
    "CAPABILITY_MAP_SCHEMA",
    "Availability",
    "CapabilityAvailability",
    "CapabilityDescriptor",
    "CapabilityError",
    "CapabilityEvidence",
    "CapabilityMap",
    "CapabilitySnapshot",
    "Maturity",
]
