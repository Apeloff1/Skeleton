"""Fail-closed inventories of Skeleton production surfaces.

This package classifies security-relevant capability surfaces. It does not
inventory source-repository provenance or compatibility shims; those live in
separate, non-overlapping gates.
"""

from skeleton.inventory.capabilities import (
    CAPABILITY_NAMES,
    CONFLICT_DOMAIN,
    SCHEMA_VERSION,
    TASK_ID,
    VERDICTS,
    CapabilityInventory,
    CapabilityRecord,
    classify_path,
    classify_text,
    inventory_from_mapping,
    inventory_paths,
    inventory_repository,
    inventory_snapshot,
)

__all__ = [
    "CAPABILITY_NAMES",
    "CONFLICT_DOMAIN",
    "SCHEMA_VERSION",
    "TASK_ID",
    "VERDICTS",
    "CapabilityInventory",
    "CapabilityRecord",
    "classify_path",
    "classify_text",
    "inventory_from_mapping",
    "inventory_paths",
    "inventory_repository",
    "inventory_snapshot",
]
