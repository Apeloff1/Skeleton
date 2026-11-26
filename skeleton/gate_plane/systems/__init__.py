"""Recovered-systems edge for the gate plane (Jeeves, GameForge, local AI, Hive).

Opt-in: apps call :func:`install_recovered_systems_edge` and mount
:func:`build_hive_router` / :func:`build_local_ai_router` themselves; nothing
here edits ``skeleton/api/server.py``. See :mod:`.edge` for the evaluation
order.
"""

from __future__ import annotations

from skeleton.gate_plane.systems.bulkhead import Bulkhead, BulkheadError, BulkheadRegistry, Permit
from skeleton.gate_plane.systems.catalog import (
    CatalogError,
    SystemCatalog,
    SystemLimits,
    SystemProfile,
    default_catalog,
)
from skeleton.gate_plane.systems.edge import (
    EdgeDecision,
    EdgeOutcome,
    EdgeRequest,
    RecoveredSystemsEdge,
    RecoveredSystemsMiddleware,
    install_recovered_systems_edge,
)
from skeleton.gate_plane.systems.headers import scrub_request_headers, scrub_response_headers
from skeleton.gate_plane.systems.hive_mount import build_hive_router
from skeleton.gate_plane.systems.local_ai_proxy import LocalAIProxy, build_local_ai_router
from skeleton.gate_plane.systems.policies import catalog_policies, catalog_routes, merge_into
from skeleton.gate_plane.systems.readiness import (
    HiveSelfCheckProbe,
    LoopbackHttpProbe,
    ProbeResult,
    ReadinessRegistry,
    ReceiptProbe,
)

__all__ = [
    "Bulkhead",
    "BulkheadError",
    "BulkheadRegistry",
    "CatalogError",
    "EdgeDecision",
    "EdgeOutcome",
    "EdgeRequest",
    "HiveSelfCheckProbe",
    "LocalAIProxy",
    "LoopbackHttpProbe",
    "Permit",
    "ProbeResult",
    "ReadinessRegistry",
    "ReceiptProbe",
    "RecoveredSystemsEdge",
    "RecoveredSystemsMiddleware",
    "SystemCatalog",
    "SystemLimits",
    "SystemProfile",
    "build_hive_router",
    "build_local_ai_router",
    "catalog_policies",
    "catalog_routes",
    "default_catalog",
    "install_recovered_systems_edge",
    "merge_into",
    "scrub_request_headers",
    "scrub_response_headers",
]
