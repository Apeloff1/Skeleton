"""Enforce source-authorized retrieval limits before private bytes can enter Jeeves context.

Read-only source checks that require eight mutually consistent stages.
Cannot authorize runtime work, read source data or grant model rights.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from . import (
    retrieved_bytes,
    source_capacity,
    chunk_count,
    signed_source,
    tenant_owner,
    manifest_hash,
    index_revision,
    stale_authority,
)

DOMAIN = "source_retrieval"
STAGES = ("retrieved_bytes", "source_capacity", "chunk_count", "signed_source", "tenant_owner", "manifest_hash", "index_revision", "stale_authority",)
STAGE_TYPES = (("retrieved_bytes", "bounded"), ("source_capacity", "capacity"), ("chunk_count", "bounded"), ("signed_source", "true"), ("tenant_owner", "same_owner"), ("manifest_hash", "sha_equal"), ("index_revision", "monotonic"), ("stale_authority", "false"),)
HANDLERS = (retrieved_bytes, source_capacity, chunk_count, signed_source, tenant_owner, manifest_hash, index_revision, stale_authority,)


def evaluate(e: object):
    """Reject unknown stages and aggregate source-claim inconsistencies."""
    if type(e) is not dict or set(e) != set(STAGES):
        raise LaptopGateHold("incomplete source_retrieval source evidence")
    checks = tuple(module.check(e[label])
                   for label, module in zip(STAGES, HANDLERS))
    if len(checks) != 8 or len({v.stage for v in checks}) != 8:
        raise LaptopGateHold("incomplete source_retrieval typed safeguard set")
    # Retain individual negative verdicts; evaluate cross-stage data only
    # after the strict input shape and local bounds have all passed.
    if all(c.accepted for c in checks) and not (e["retrieved_bytes"]["used"] <= e["source_capacity"]["reserved"]):
        raise LaptopGateHold("contradictory source_retrieval source observations")
    return checks


def contracts() -> tuple[dict[str, object], ...]:
    """Eight fixed stage contracts; no source-only release permission."""
    return tuple(module.contract() for module in HANDLERS)


__all__ = ["STAGES", "STAGE_TYPES", "evaluate", "contracts"]
