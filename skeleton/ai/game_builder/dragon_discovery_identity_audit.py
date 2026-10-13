"""Exact-blob custody audit for the Dragon raw-link expansion handoff.

Two frozen accepted-cohort identity manifests bridge the original 10,770 raw
supplement leads to the newer 4,053 source references. This read-only audit
verifies the manifest itself against Git blob identity, source digests, and the
complete 19,228-link chain; raw URLs remain unreviewed discovery metadata.
"""
from __future__ import annotations

from hashlib import sha1, sha256
import json
from pathlib import Path

from .dragon_almanacs import read_source_registry
from .dragon_discovery_reconciled import (
    EXPECTED_RAW_TOTAL, SOURCE_BATCHES, EXCLUDED_ORPHANS,
    verify_reconciled_chain,
)
from .dragon_discovery_admission import _supplement


MANIFESTS = (
    "machine/dragon_raw_lead_identity_cohort_a_20261012.json",
    "machine/dragon_raw_lead_identity_cohort_b_20261012.json",
)
PREVIOUS_SUPPLEMENT_COUNT = 10_770
PREVIOUS_BATCH_COUNT = 16
SOURCE_SHA = "source-"


def _git_blob_sha(data: bytes) -> str:
    return sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def audit_raw_discovery_identity(registry: dict, *, detail_limit: int = 15) -> dict:
    """Prove the incremental raw-link inventory without reading linked content.

    A correct Git object SHA means the source file bytes match the local claim,
    NOT that GitHub is an independent trusted attestation or that linked source
    material has any specific copyright, use or training permission.
    """
    if type(detail_limit) is not int or not 0 <= detail_limit <= 100:
        raise ValueError("invalid source manifest audit detail budget")
    root = Path(__file__).resolve().parents[3]
    expected = list(SOURCE_BATCHES[:PREVIOUS_BATCH_COUNT])
    claimed = []
    receipt_ids = set()
    manifest_paths = []
    manifest_summaries = []
    for manifest_name in MANIFESTS:
        file = root / manifest_name
        if file.is_symlink() or not file.is_file():
            raise ValueError("raw identity manifest regular file required")
        raw = file.read_bytes()
        if not 1 <= len(raw) <= 2_000_000:
            raise ValueError("raw identity manifest byte or file custody invalid")
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ValueError("raw identity manifest JSON invalid") from exc
        if (not isinstance(manifest, dict)
                or manifest.get("schema") !=
                   "skeleton.dragon.raw_discovery_dedup_index.v1"
                or manifest.get("rights_approved") is not False
                or manifest.get("training_authorized") is not False
                or not isinstance(manifest.get("source_files"), list)
                or not isinstance(manifest.get("source_ids"), list)
                or manifest.get("raw_count") != len(manifest["source_ids"])):
            raise ValueError("raw identity manifest claims invalid")
        ordered_ids = manifest["source_ids"]
        if (ordered_ids != sorted(ordered_ids) or
                len(ordered_ids) != len(set(ordered_ids)) or
                any(not isinstance(sid, str) or len(sid) != 71 or
                    not sid.startswith(SOURCE_SHA) or
                    any(c not in "0123456789abcdef" for c in sid[7:])
                    for sid in ordered_ids)):
            raise ValueError("malformed or duplicated raw identity")
        current = []
        for item in manifest["source_files"]:
            if (not isinstance(item, dict)
                    or set(item) != {"path", "blob_sha", "count"}
                    or not isinstance(item["path"], str)
                    or item["path"] not in expected
                    or item["path"] in claimed):
                raise ValueError("raw source evidence manifest path collision")
            path = root / item["path"]
            payload = path.read_bytes()
            if (_git_blob_sha(payload) != item["blob_sha"]
                    or type(item["count"]) is not int
                    or not 0 < item["count"] <= 10_000):
                raise ValueError("raw source Git blob identity changed")
            source_path, doc = _supplement(path)
            if source_path != item["path"] or len(doc["candidates"]) != item["count"]:
                raise ValueError("raw source manifest count or pathname changed")
            current.extend(row["source_id"] for row in doc["candidates"])
            claimed.append(item["path"])
        if sorted(current) != ordered_ids or receipt_ids.intersection(ordered_ids):
            raise ValueError("raw identity manifest no longer matches accepted links")
        receipt_ids.update(ordered_ids)
        manifest_paths.append(manifest_name)
        manifest_summaries.append({
            "manifest": manifest_name,
            "verified_raw_links": len(ordered_ids),
            "verified_source_files": len(manifest["source_files"]),
            "source_contents_verified": False,
            "training_authorized": False,
        })
    if (claimed != expected or len(receipt_ids) != PREVIOUS_SUPPLEMENT_COUNT
            or len(SOURCE_BATCHES) <= PREVIOUS_BATCH_COUNT):
        raise ValueError("accepted discovery cohort source coverage differs")
    additions = set()
    added = 0
    for path in SOURCE_BATCHES[PREVIOUS_BATCH_COUNT:]:
        _, doc = _supplement(root / path)
        for row in doc["candidates"]:
            sid = row["source_id"]
            if sid in receipt_ids or sid in additions:
                raise ValueError("new raw discovery duplicates historical receipt")
            if sid != "source-" + sha256(row["url"].encode("utf-8")).hexdigest():
                raise ValueError("new source ID does not bind raw URL")
            additions.add(sid)
            added += 1
    full = verify_reconciled_chain(registry)
    if (full["raw_url_leads"] != EXPECTED_RAW_TOTAL
            or len(receipt_ids) + added + registry["unique_urls"]
                != EXPECTED_RAW_TOTAL):
        raise ValueError("source growth does not reconcile with checked full chain")
    return {
        "schema": "skeleton.dragon.discovery_identity_audit.v1",
        "baseline_raw_links": registry["unique_urls"],
        "historical_supplement_raw_links": len(receipt_ids),
        "additional_pinned_raw_links": added,
        "reconciled_raw_links": full["raw_url_leads"],
        "canonical_candidate_urls": full["canonical_candidate_sources"],
        "accepted_source_batches": len(SOURCE_BATCHES),
        "excluded_orphans": list(EXCLUDED_ORPHANS),
        "historical_manifests": manifest_summaries[:detail_limit],
        "historical_manifests_omitted": max(0,len(manifest_summaries)-detail_limit),
        "all_source_blob_identities_checked": True,
        "linked_source_contents_verified": False,
        "crawler_authorized": False,
        "rights_approved": False,
        "training_authorized": False,
        "memory_promotion_authorized": False,
    }
