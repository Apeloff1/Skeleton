"""Import-light audit snapshot for Pack A admit depth surfaces."""

from __future__ import annotations

from typing import Any, Dict, Final

from skeleton.kernel.pack_a.priority_table import PRIORITY_TABLE, table_size
from skeleton.kernel.pack_a.buffer_arena import ROUTE_CLASS_MIN_SIZE, STAGING_RECIPES
from skeleton.kernel.pack_a.coalesce_depth import COALESCE_NAMESPACES
from skeleton.kernel.pack_a.tiered_depth import PACK_A_CACHE_NAMESPACES

PACK_A_ADMIT_DEPTH_AUDIT_KIND: Final = "pack_a_admit_depth_audit"


def pack_a_admit_depth_audit_snapshot() -> Dict[str, Any]:
    return {
        "kind": PACK_A_ADMIT_DEPTH_AUDIT_KIND,
        "priority_table_size": table_size(),
        "priority_classes": sorted({row[1] for row in PRIORITY_TABLE}),
        "route_class_min_sizes": dict(ROUTE_CLASS_MIN_SIZE),
        "staging_recipe_count": len(STAGING_RECIPES),
        "coalesce_namespaces": list(COALESCE_NAMESPACES),
        "cache_namespaces": list(PACK_A_CACHE_NAMESPACES),
        "modules": [
            "skeleton.kernel.pack_a.buffer_arena",
            "skeleton.kernel.pack_a.coalesce_depth",
            "skeleton.kernel.pack_a.tiered_depth",
            "skeleton.kernel.pack_a.metrics",
            "skeleton.api.pack_a.admit_depth",
            "skeleton.api.pack_a.admit_buffers",
            "skeleton.api.pack_a.admit_decision_cache",
            "skeleton.api.pack_a.priority_table",
        ],
    }


__all__ = ["PACK_A_ADMIT_DEPTH_AUDIT_KIND", "pack_a_admit_depth_audit_snapshot"]
