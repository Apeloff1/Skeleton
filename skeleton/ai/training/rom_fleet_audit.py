"""Verify completed ROM training across a frozen fleet without running game content.

This is a bounded, read-only accounting view of already-produced evidence.
Coverage is measured per distinct operator-approved source identity, never per
filename or per replay, and existing receipts remain immutable.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .rom_inventory_snapshot import frozen_inventory_page, load_frozen_inventory
from .rom_study import (
    RomStudyError, _load_approvals, _private_output, verified_rom_receipt,
)

SCHEMA = "skeleton.jeeves.rom_fleet_audit.v1"
_MAX_CANDIDATES_PER_SOURCE = 128
_RECEIPT_NAME = re.compile(r"rom-[0-9a-f]{16}-[0-9a-f]{16}\.json\Z")


def audit_fleet_page(root: Path, snapshot_file: Path, approvals_file: Path,
                     receipts_dir: Path, *, cursor: str | None = None,
                     limit: int = 64) -> dict[str, Any]:
    """Audit one frozen page; no emulator execution, neural training or promotion.

    A source is covered only if an exact, unchanged, rights-reviewed
    file has at least one independently checked receipt from the same
    approval manifest AND same frozen library. A repeated file path does
    not inflate distinct-ROM training counts.
    """
    snapshot = load_frozen_inventory(snapshot_file, root=root)
    page = frozen_inventory_page(snapshot, root=root, cursor=cursor, limit=limit)
    approved, approval_sha = _load_approvals(approvals_file)
    receipts_dir = _private_output(receipts_dir)
    entries: list[dict[str, Any]] = []
    unique_in_snapshot = {}
    for item in snapshot["entries"]:
        identity = item["file_sha256"]
        if identity not in unique_in_snapshot:
            unique_in_snapshot[identity] = item["relative_path"]
    counts = {
        "candidate_files": 0, "distinct_sources_in_page": 0,
        "verified_q_policy_sources": 0,
        "verified_neural_candidate_sources": 0,
        "verified_executed_without_q_updates": 0,
        "rights_review_required": 0, "source_identity_changed": 0,
        "approved_but_no_receipt": 0,
        "invalid_or_stale_receipt_sources": 0,
        "duplicates_not_retrained": 0,
    }
    for row in page["rows"]:
        counts["candidate_files"] += 1
        name = row["relative_path"]
        digest = row.get("file_sha256")
        entry = {"relative_path": name, "source_sha256": digest}
        if digest is None:
            entry["status"] = "source_identity_changed"
            counts["source_identity_changed"] += 1
            entries.append(entry)
            continue
        if unique_in_snapshot[digest] != name:
            entry["status"] = "duplicate_source_inventory_alias"
            entry["canonical_relative_path"] = unique_in_snapshot[digest]
            counts["duplicates_not_retrained"] += 1
            entries.append(entry)
            continue
        counts["distinct_sources_in_page"] += 1
        grant = approved.get(digest)
        if grant is None:
            entry["status"] = "rights_review_required"
            counts["rights_review_required"] += 1
            entries.append(entry)
            continue
        if grant["content_size_bytes"] != row["size_bytes"]:
            entry["status"] = "source_identity_changed"
            counts["source_identity_changed"] += 1
            entries.append(entry)
            continue
        pattern = "rom-" + digest[:16] + "-*.json"
        options = sorted(receipts_dir.glob(pattern))
        if len(options) > _MAX_CANDIDATES_PER_SOURCE:
            entry["status"] = "receipt_capacity_exceeded"
            counts["invalid_or_stale_receipt_sources"] += 1
            entries.append(entry)
            continue
        audited = []
        rejected = 0
        for path in options:
            if not _RECEIPT_NAME.fullmatch(path.name):
                rejected += 1
                continue
            try:
                proof = verified_rom_receipt(path, expected_source_sha256=digest)
                if (proof["approval_manifest_sha256"] != approval_sha
                        or proof["frozen_inventory_sha256"] != snapshot["inventory_sha256"]
                        or proof["source_size_bytes"] != row["size_bytes"]
                        or proof["target_id"] != grant["target_id"]
                        or proof["core_id"] != grant["core_id"]
                        or proof["content_bundle_sha256"] != grant.get("bundle_sha256")):
                    rejected += 1
                    continue
                audited.append({
                    "receipt_sha256": proof["receipt_sha256"],
                    "receipt_name": path.name,
                    "q_updates": proof["actual_q_table_updates"],
                    "steps": proof["actual_training_steps"],
                    "neural_candidate_status": proof["neural_candidate_status"],
                    "neural_candidate_optimizer_steps": proof["neural_candidate_optimizer_steps"],
                })
            except (ValueError, OSError):
                rejected += 1
        if audited:
            trained = any(value["q_updates"] > 0 for value in audited)
            neural = any(
                value["neural_candidate_status"] ==
                "candidate_trained_requires_independent_review"
                and value["neural_candidate_optimizer_steps"] > 0
                for value in audited
            )
            entry.update({
                "status": ("verified_q_policy_updated"
                           if trained else "verified_executed_without_q_update"),
                "verified_receipt_count": len(audited),
                "rejected_receipt_count": rejected,
                "max_q_updates_single_run": max(x["q_updates"] for x in audited),
                "max_steps_single_run": max(x["steps"] for x in audited
                                            if type(x["steps"]) is int),
                "neural_candidate_trained": neural,
                "receipt_sha256": [item["receipt_sha256"] for item in audited],
                "production_jeeves_weights_modified": False,
            })
            if trained:
                counts["verified_q_policy_sources"] += 1
            else:
                counts["verified_executed_without_q_updates"] += 1
            if neural:
                counts["verified_neural_candidate_sources"] += 1
        elif rejected:
            entry["status"] = "invalid_or_stale_receipt_only"
            entry["rejected_receipt_count"] = rejected
            counts["invalid_or_stale_receipt_sources"] += 1
        else:
            entry["status"] = "approved_but_no_receipt"
            counts["approved_but_no_receipt"] += 1
        entries.append(entry)
    denominator = counts["distinct_sources_in_page"]
    coverage = round(100.0 * (
        counts["verified_q_policy_sources"] +
        counts["verified_executed_without_q_updates"]
    ) / denominator, 2) if denominator else 0.0
    return {
        "schema_version": SCHEMA,
        "inventory_sha256": snapshot["inventory_sha256"],
        "approval_manifest_sha256": approval_sha,
        "inventory_cursor": page["cursor"], "next_cursor": page["next_cursor"],
        "finished_inventory": page["finished"],
        "total_snapshot_candidate_files": len(snapshot["entries"]),
        "page_counts": counts,
        "source_execution_coverage_pct": coverage,
        "source_execution_coverage_scope": "distinct_source_identities_on_this_page_only",
        "production_jeeves_weights_modified": False,
        "emulator_or_optimizer_executed": False,
        "rows": entries,
    }
