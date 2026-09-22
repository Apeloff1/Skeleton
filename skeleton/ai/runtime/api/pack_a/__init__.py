"""Pack A API admit depth — BufferPool/Coalescer/TieredCache wiring."""

from __future__ import annotations

from skeleton.api.pack_a.admit_depth import (
    AdmitDepthContext,
    AdmitDepthResult,
    DeepWriteAdmit,
    PriorityResolver,
    RouteClass,
    admit_write_deep,
    default_deep_admit,
    reset_default_deep_admit_for_tests,
)
from skeleton.api.pack_a.admit_buffers import (
    AdmitBodyStager,
    BoundBody,
    stage_mutating_body,
)
from skeleton.api.pack_a.admit_decision_cache import (
    DecisionCacheFacade,
    cached_admit_outcome,
)
from skeleton.api.pack_a.admit_scenarios import SCENARIOS, scenario_count
from skeleton.api.pack_a.path_catalog import catalog_count, SYNTHETIC_PATHS
from skeleton.api.pack_a.priority_table import (
    PRIORITY_TABLE,
    priority_for_path,
    route_class_for_path,
)

__all__ = [
    "SCENARIOS",
    "SYNTHETIC_PATHS",
    "catalog_count",
    "scenario_count",
    "AdmitBodyStager",
    "AdmitDepthContext",
    "AdmitDepthResult",
    "BoundBody",
    "DecisionCacheFacade",
    "DeepWriteAdmit",
    "PRIORITY_TABLE",
    "PriorityResolver",
    "RouteClass",
    "admit_write_deep",
    "cached_admit_outcome",
    "default_deep_admit",
    "priority_for_path",
    "reset_default_deep_admit_for_tests",
    "route_class_for_path",
    "stage_mutating_body",
]
