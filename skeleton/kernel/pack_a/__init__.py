"""Pack A — ultra-infra depth over BufferPool / Coalescer / TieredCache.

Extend-only Backend hardening. Re-exports deepened helpers without
replacing the thin gf-services ports in ``skeleton.kernel`` roots.
"""

from __future__ import annotations

from skeleton.kernel.pack_a.buffer_arena import (
    ArenaStats,
    BodyStagingPool,
    BufferArena,
    ClassHistogram,
    DefaultPoolHolder,
    LeaseGuard,
    OverflowLedger,
    PooledByteView,
    StagingLease,
    arena_for_content_length,
    default_body_pool,
    default_pool,
    reset_default_pools_for_tests,
)
from skeleton.kernel.pack_a.coalesce_depth import (
    CoalesceMetrics,
    CoalesceTimeout,
    FlightRecord,
    KeyedFlightBoard,
    WaiterLimitExceeded,
    WaiterQueue,
    coalesce_get_or_compute,
    default_board,
    reset_default_board_for_tests,
)
from skeleton.kernel.pack_a.tiered_depth import (
    AdmitDecision,
    AdmitDecisionCache,
    CacheNamespace,
    ChaosCachePolicy,
    NamespacedTieredCache,
    PrefixInvalidator,
    StampedeSafeCache,
    TierStats,
    default_admit_cache,
    default_namespaced_cache,
    reset_default_caches_for_tests,
)
from skeleton.kernel.pack_a.staging_matrix import STAGING_MATRIX, matrix_stats
from skeleton.kernel.pack_a.telemetry_bridge import TelemetryBridge, snapshot_event
from skeleton.kernel.pack_a.metrics import (
    CounterVec,
    GaugeVec,
    HistogramVec,
    InfraMeter,
    MeterSnapshot,
    default_meter,
    reset_default_meter_for_tests,
)

__all__ = [
    "STAGING_MATRIX",
    "TelemetryBridge",
    "matrix_stats",
    "snapshot_event",
    "AdmitDecision",
    "AdmitDecisionCache",
    "ArenaStats",
    "BodyStagingPool",
    "BufferArena",
    "CacheNamespace",
    "ChaosCachePolicy",
    "ClassHistogram",
    "CoalesceMetrics",
    "CoalesceTimeout",
    "CounterVec",
    "DefaultPoolHolder",
    "FlightRecord",
    "GaugeVec",
    "HistogramVec",
    "InfraMeter",
    "KeyedFlightBoard",
    "LeaseGuard",
    "MeterSnapshot",
    "NamespacedTieredCache",
    "OverflowLedger",
    "PooledByteView",
    "PrefixInvalidator",
    "StagingLease",
    "StampedeSafeCache",
    "TierStats",
    "WaiterLimitExceeded",
    "WaiterQueue",
    "arena_for_content_length",
    "coalesce_get_or_compute",
    "default_admit_cache",
    "default_board",
    "default_body_pool",
    "default_meter",
    "default_namespaced_cache",
    "default_pool",
    "reset_default_board_for_tests",
    "reset_default_caches_for_tests",
    "reset_default_meter_for_tests",
    "reset_default_pools_for_tests",
]
