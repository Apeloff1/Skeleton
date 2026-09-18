"""Quality-plane inventories and fail-closed classifiers.

``skeleton.quality`` is read-mostly evidence. It does not own replay harnesses,
concept-to-release scoring, or mechanics replay.
"""

from skeleton.quality.property_inventory import (
    CONFLICT_DOMAIN,
    CoverageRow,
    CoverageStatus,
    InventoryReport,
    PropertyEvidence,
    PropertyInventoryError,
    SCHEMA,
    SCHEMA_VERSION,
    SEED,
    SubsystemInvariant,
    TASK_ID,
    classify_coverage,
    default_catalog,
    gaps,
    inventory_property_coverage,
    normalize_status,
)

__all__ = [
    "CONFLICT_DOMAIN",
    "CoverageRow",
    "CoverageStatus",
    "InventoryReport",
    "PropertyEvidence",
    "PropertyInventoryError",
    "SCHEMA",
    "SCHEMA_VERSION",
    "SEED",
    "SubsystemInvariant",
    "TASK_ID",
    "classify_coverage",
    "default_catalog",
    "gaps",
    "inventory_property_coverage",
    "normalize_status",
]
