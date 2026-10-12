"""Fail-closed operator entry for the complete, reconciled source evidence lane.

The previous independent batch 0024 and orphaned batch 0030 do not form a
consecutive custody chain. Their pinned catalog discoveries were reconciled
into audited consecutive batches 0031..0037; further, twelve new source
catalogs extend this custody lineage through 0038..0042, including seven
more retro, Godot, Unity and game-editor reference collections. Excluded orphans
never appear as asserted ancestors or training grants.
"""
from __future__ import annotations

from pathlib import Path

from .dragon_almanacs import DragonAlmanacs, _auth
from .dragon_discovery_admission import (
    DragonDiscoveryAdmission, _supplement, validate_discovery_chain,
)

EXPECTED_RAW_TOTAL = 15_175
SOURCE_BATCHES = (
    "docs/ai/evidence/dragon-source-expansion-20261011-batch-0020.json",
    *(
        f"docs/ai/evidence/dragon-source-expansion-20261012-batch-{n:04d}.json"
        for n in (21, 22, 23, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42)
    ),
)
EXCLUDED_ORPHANS = (
    "docs/ai/evidence/dragon-source-expansion-20261012-batch-0024.json",
    "docs/ai/evidence/dragon-source-expansion-20261012-batch-0030.json",
)


def _chain() -> list[tuple[str, dict]]:
    root = Path(__file__).resolve().parents[3]
    paths = [root / relative for relative in SOURCE_BATCHES]
    if len(paths) != len(set(paths)) or any(
            not str(path).startswith(str(root)) for path in paths):
        raise ValueError("noncanonical discovery evidence paths")
    return [_supplement(path) for path in paths]


def verify_reconciled_chain(registry: dict) -> dict:
    """Validate every original URL, archive pin, parent and raw count, read-only."""
    evidence = _chain()
    snapshot = validate_discovery_chain(registry, evidence)
    if (snapshot["raw_total_discovered"] != EXPECTED_RAW_TOTAL
            or snapshot["raw_new"] != EXPECTED_RAW_TOTAL - registry["unique_urls"]
            or len(evidence) != len(SOURCE_BATCHES)):
        raise ValueError("reconciled evidence chain does not match frozen count")
    return {
        "schema": "skeleton.dragon.reconciled_discovery_chain.v1",
        "raw_url_leads": snapshot["raw_total_discovered"],
        "raw_new": snapshot["raw_new"],
        "canonical_candidate_sources": snapshot["total_discovered"],
        "canonical_new": snapshot["new"],
        "evidence_batch_paths": list(SOURCE_BATCHES),
        "excluded_orphan_paths": list(EXCLUDED_ORPHANS),
        "source_content_verified": False,
        "crawler_authorized": False,
        "rights_approved": False,
        "training_authorized": False,
        "memory_promotion_authorized": False,
    }


def import_reconciled_chain(almanacs: DragonAlmanacs, owner: str,
                            registry: dict, *, authorized: bool) -> dict:
    """Import metadata and seed policy-stage jobs, never authorize actual crawl."""
    _auth(owner, authorized)
    verify_reconciled_chain(registry)
    result = DragonDiscoveryAdmission(almanacs).import_chain(
        owner, registry, _chain(), authorized=True)
    result["reconciled_raw_url_leads"] = EXPECTED_RAW_TOTAL
    result["excluded_orphan_paths"] = list(EXCLUDED_ORPHANS)
    result["source_content_verified"] = False
    result["rights_approved"] = False
    result["training_authorized"] = False
    return result
