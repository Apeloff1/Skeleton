"""Read-only, replay-verified delta between two pinned original-game cohorts.

A release planner can inspect exact source and gameplay changes without
executing native binaries, trusting a package-supplied pin, or mutating either
cohort. Both sides must independently pass the canonical offline verifier.
"""
from __future__ import annotations

from pathlib import Path

from .contracts import canonical_digest
from .offline_export_batch import verify_export_batch

SCHEMA = "skeleton.game_builder.offline_export_batch_delta.v1"


def compare_export_batches(
    left_root: str | Path, right_root: str | Path, *,
    left_index_sha256: str, right_index_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Classify verified package additions, removals, content changes and moves."""
    if authorized is not True:
        raise PermissionError("operator authorization required for batch comparison")
    left = verify_export_batch(
        left_root, expected_index_sha256=left_index_sha256, authorized=True,
    )
    right = verify_export_batch(
        right_root, expected_index_sha256=right_index_sha256, authorized=True,
    )
    previous = {entry["project_id"]: entry for entry in left["packages"]}
    current = {entry["project_id"]: entry for entry in right["packages"]}
    changes: list[dict[str, object]] = []
    for project_id in sorted(set(previous) | set(current)):
        before = previous.get(project_id)
        after = current.get(project_id)
        if before is None:
            kind = "added"
        elif after is None:
            kind = "removed"
        elif before["manifest_sha256"] != after["manifest_sha256"]:
            kind = "source_changed"
        elif before["package_dir"] != after["package_dir"]:
            kind = "relocated"
        else:
            kind = "unchanged"
        changes.append({
            "project_id": project_id,
            "kind": kind,
            "before_manifest_sha256": (
                before["manifest_sha256"] if before else None
            ),
            "after_manifest_sha256": (
                after["manifest_sha256"] if after else None
            ),
            "before_package_dir": before["package_dir"] if before else None,
            "after_package_dir": after["package_dir"] if after else None,
            "before_replay_digest": before["replay_digest"] if before else None,
            "after_replay_digest": after["replay_digest"] if after else None,
        })
    counts = {
        kind: sum(change["kind"] == kind for change in changes)
        for kind in ("added", "removed", "source_changed", "relocated", "unchanged")
    }
    body = {
        "schema": SCHEMA,
        "left_index_sha256": left_index_sha256,
        "right_index_sha256": right_index_sha256,
        "left_receipt_digest": left["receipt_digest"],
        "right_receipt_digest": right["receipt_digest"],
        "left_verified_packages": left["verified_packages"],
        "right_verified_packages": right["verified_packages"],
        "classification_counts": counts,
        "changes": changes,
        "both_cohorts_replayed": True,
        "migration_applied": False,
        "native_execution_verified": False,
        "release_certified": False,
    }
    return {**body, "receipt_digest": canonical_digest(body)}


__all__ = ["compare_export_batches", "SCHEMA"]
