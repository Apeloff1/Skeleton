"""Pack C — cortex hybrid expansion (Internal Systems).

Extend-only pack. Locks hybrid invariants:
- PFC small LM uses LearnedWeights(..., attn=False)
- unfitted neo amalgam returns kind="own" (no lm tag / no decode)
- error lattice remains importable
"""
from __future__ import annotations

from skeleton.cortex.pack_c.amalgam_policy import (
    AmalgamDecision,
    AmalgamPolicy,
    decide_amalgam,
    assert_unfitted_invariants,
    assert_fitted_invariants,
    evaluate_matrix,
)
from skeleton.cortex.pack_c.hybrid_router import HybridRouter, Stimulus, RoutePlan, plan_board
from skeleton.cortex.pack_c.ledger_hybrid import HybridLedger, LedgerEntry, seed_ledger
from skeleton.cortex.pack_c.telemetry import CortexPackTelemetry, PackSnapshot, warm_telemetry
from skeleton.cortex.pack_c.moe_bridge import MoEBridge, MoEBridgeConfig, build_default_bridge
from skeleton.cortex.pack_c.persistence import HybridPersistence, SnapshotError, demo_state
from skeleton.cortex.pack_c.scenarios import SCENARIO_CATALOG, scenario_by_id, assert_catalog_locks
from skeleton.cortex.pack_c.depth_matrix import DEPTH_BANDS, pfc_depth_always_zero
from skeleton.cortex.pack_c.queue_lattice import QUEUE_LATTICE, assert_pfc_queue_no_transformer
from skeleton.cortex.pack_c.sigil_survival import survive, run_sigil_battery
from skeleton.cortex.pack_c.contracts import PackCManifest, ConstraintLock
from skeleton.cortex.pack_c.operations import PackCOperations
from skeleton.cortex.pack_c.evidence import PackCEvidence

__all__ = [
    "AmalgamDecision",
    "AmalgamPolicy",
    "decide_amalgam",
    "assert_unfitted_invariants",
    "assert_fitted_invariants",
    "evaluate_matrix",
    "HybridRouter",
    "Stimulus",
    "RoutePlan",
    "plan_board",
    "HybridLedger",
    "LedgerEntry",
    "seed_ledger",
    "CortexPackTelemetry",
    "PackSnapshot",
    "warm_telemetry",
    "MoEBridge",
    "MoEBridgeConfig",
    "build_default_bridge",
    "HybridPersistence",
    "SnapshotError",
    "demo_state",
    "SCENARIO_CATALOG",
    "scenario_by_id",
    "assert_catalog_locks",
    "DEPTH_BANDS",
    "pfc_depth_always_zero",
    "QUEUE_LATTICE",
    "assert_pfc_queue_no_transformer",
    "survive",
    "run_sigil_battery",
    "PackCManifest",
    "ConstraintLock",
    "PackCOperations",
    "PackCEvidence",
]

PACK_C_VERSION = "2026.09.20"
PACK_C_NAME = "cortex-hybrid"
