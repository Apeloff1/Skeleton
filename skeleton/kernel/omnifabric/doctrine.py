"""OmniFabric doctrine notes — ported from gameforge-rs fabric module docs.

These constants and narratives document the forge-path contract for
reviewers. They are importable so tests and routes can assert the same
labels the RS empire uses.
"""
from __future__ import annotations

SIBLING_REPO = "Apeloff1/gameforge-rs"
SIBLING_PATH = "crates/gf-gameforge/src/lib.rs"
SIBLING_MODULE = "fabric::OmniFabric"

DOCTRINE = {
    "events_are_truth": (
        "One immutable fact in the omnifabric. Events are the only truth; "
        "projections are derived, disposable, rebuildable."
    ),
    "journal_first": (
        "Append order is law: journal to the outbox FIRST, then admit to the "
        "hot tail. A crash leaves intent journaled and replayable — the event "
        "can never exist only in memory."
    ),
    "backpressure_not_drop": (
        "If the outbox is full, the append fails loud — durability "
        "backpressures, it never drops."
    ),
    "hash_chain_f5": (
        "Every event chains to its predecessor. Verify the chain by "
        "recomputing hashes from genesis to head — a tampered history cannot "
        "produce a valid head."
    ),
    "f1_sha256": (
        "Every digest in the empire is SHA-256. Decision keys and fabric "
        "hashes share one digest law."
    ),
    "proof_as_route": (
        "verify_chain recomputes genesis→head on demand; the HTTP surface "
        "exposes the proof as a route, not a promise."
    ),
}

COLLECTION = "omega_fabric"
GENESIS = "genesis"
DEFAULT_HOT_CAP = 2048
DEFAULT_OUTBOX_CAP = 4096

ROUTE_PREFIX = "/omnifabric"
ROUTE_PATHS = (
    "/omnifabric/append",
    "/omnifabric/tail",
    "/omnifabric/verify-chain",
    "/omnifabric/status",
    "/omnifabric/query",
    "/omnifabric/reconcile",
    "/omnifabric/checkpoint",
    "/omnifabric/ledgers",
)


def doctrine_blurb() -> str:
    return " | ".join(f"{k}: {v}" for k, v in DOCTRINE.items())


PORT_NOTES = """
Hex OmniFabric port notes (feat/throughput-forge-sibling-port-20260920)
=====================================================================

Scope: ONE coherent surface — fabric::OmniFabric from Apeloff1/gameforge-rs
into skeleton/kernel/omnifabric. Δ-Memory and SagaRegistry are owned by
sibling agents and are intentionally absent from this branch.

Extend-only rules observed:
- No edits to skeleton/api/server.py lifespan or router includes
- No stomping security PRs (#1640/#1644/#1646)
- backend/zaibatsu/fabric.py left untouched; hex is the preferred path
- Standalone FastAPI router at skeleton/api/omnifabric_routes.py

Module map:
- events / codecs / errors — FabricEvent + F1 SHA-256 canonical law
- outbox — gf_core::outbox journal-first durability
- core — OmniFabric append / verify_chain / tail / hot-cap drain
- ledgers / projections / subscribers / metrics — forge-path indexes
- verify / merkle / windows / segment / persistence — proof + history
- service — cohesive facade for routes and callers
- batch / replay / adapters / audit / doctrine — supporting surface

Tests live under skeleton/testing/test_omnifabric_*.py.
"""


def port_summary() -> dict[str, object]:
    return {
        "sibling_repo": SIBLING_REPO,
        "sibling_path": SIBLING_PATH,
        "sibling_module": SIBLING_MODULE,
        "collection": COLLECTION,
        "routes": list(ROUTE_PATHS),
        "doctrine_keys": sorted(DOCTRINE.keys()),
        "notes": PORT_NOTES.strip().splitlines()[0],
    }
