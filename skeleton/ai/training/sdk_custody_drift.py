"""Versioned, redacted SDK source-drift snapshots for governed Jeeves intake.

Snapshots are constructed from validate_sources() results; changes require
fresh operator rights review. Unkeyed digests are integrity pins, NOT signatures.
No SDK binaries, proprietary documentation or prompt/answer bodies are exported.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .sdk_study import SDK_SCHEMA, SDKStudyError, MAX_SDKS, MAX_DOCS

SNAPSHOT_SCHEMA = "skeleton.jeeves.sdk_custody_snapshot.v1"
DRIFT_SCHEMA = "skeleton.jeeves.sdk_custody_drift.v1"


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def custody_snapshot(report: dict, sources: dict[str, dict]) -> dict:
    """Reduce a previously validated SDK manifest to a redacted immutable index."""
    if (type(report) is not dict or report.get("schema_version") != SDK_SCHEMA
            or not isinstance(report.get("manifest_sha256"), str)
            or type(sources) is not dict
            or len(sources) > MAX_SDKS * MAX_DOCS
            or report.get("pinned_documents") != len(sources)):
        raise SDKStudyError("validated SDK manifest and source index required")
    rows = []
    keys = set()
    for sha, item in sorted(sources.items()):
        if (type(sha) is not str or len(sha) != 64
                or any(c not in "0123456789abcdef" for c in sha)
                or type(item) is not dict):
            raise SDKStudyError("SDK document hash identity is malformed")
        sdk, path, version = item.get("sdk_id"), item.get("document"), item.get("version")
        if not all(isinstance(value, str) and value for value in (sdk, path, version)):
            raise SDKStudyError("SDK provenance descriptor absent")
        key = (sdk, path)
        if key in keys:
            raise SDKStudyError("ambiguous SDK document path identity")
        keys.add(key)
        rights = item.get("rights")
        targets = item.get("target_ids")
        if (type(rights) is not dict or type(item.get("trainable")) is not bool
                or not isinstance(targets, (tuple, list))
                or not all(isinstance(target, str) for target in targets)):
            raise SDKStudyError("SDK source lacks checked rights or target descriptor")
        rows.append({
            "sdk_id": sdk, "path": path, "version": version,
            "sha256": sha, "sdk_kind": item.get("sdk_kind"),
            "target_ids": sorted(targets),
            "trainable": item["trainable"],
            "rights_review_digest": _digest(rights),
        })
    result = {
        "schema_version": SNAPSHOT_SCHEMA,
        "source_manifest_sha256": report["manifest_sha256"],
        "document_count": len(rows),
        "documents": sorted(rows, key=lambda row: (row["sdk_id"], row["path"])),
        "actual_sdk_execution": False,
        "training_performed": False,
    }
    result["snapshot_digest"] = _digest(result)
    return result


def _verify(snapshot: dict) -> dict[tuple[str, str], dict]:
    if (type(snapshot) is not dict
            or snapshot.get("schema_version") != SNAPSHOT_SCHEMA
            or type(snapshot.get("documents")) is not list
            or len(snapshot["documents"]) > MAX_SDKS * MAX_DOCS
            or snapshot.get("document_count") != len(snapshot["documents"])
            or snapshot.get("snapshot_digest") != _digest({
                key: value for key, value in snapshot.items()
                if key != "snapshot_digest"
            })):
        raise SDKStudyError("SDK custody snapshot is altered or exceeds bounds")
    indexed = {}
    for item in snapshot["documents"]:
        if type(item) is not dict:
            raise SDKStudyError("SDK source identity must be an object")
        identity = (item.get("sdk_id"), item.get("path"))
        if (not all(isinstance(x, str) and x for x in identity)
                or identity in indexed):
            raise SDKStudyError("duplicated or invalid SDK document identity")
        indexed[identity] = item
    return indexed


def compare_custody(before: dict, after: dict) -> dict:
    """Identify loss, additions and changes requiring a fresh reviewed corpus."""
    previous, current = _verify(before), _verify(after)
    changes = []
    for sdk_id, path in sorted(previous.keys() | current.keys()):
        old, new = previous.get((sdk_id, path)), current.get((sdk_id, path))
        if old is None:
            state = "new_document_requires_review"
        elif new is None:
            state = "document_removed_or_deauthorized"
        elif old == new:
            continue
        elif old.get("trainable") is True and new.get("trainable") is not True:
            state = "training_authority_revoked"
        elif old.get("sha256") != new.get("sha256"):
            state = "source_bytes_changed_require_review"
        elif old.get("rights_review_digest") != new.get("rights_review_digest"):
            state = "rights_review_changed_require_reapproval"
        elif old.get("version") != new.get("version"):
            state = "sdk_version_changed_require_reapproval"
        else:
            state = "target_or_metadata_changed_require_review"
        changes.append({
            "sdk_id": sdk_id, "path": path, "change": state,
            "old_source_sha256": old["sha256"] if old else None,
            "new_source_sha256": new["sha256"] if new else None,
            "previously_trainable": old.get("trainable") if old else False,
            "currently_declared_trainable": new.get("trainable") if new else False,
            "held_out_corpus_revalidation_required": True,
            "automatic_train_or_promotion": False,
        })
    result = {
        "schema_version": DRIFT_SCHEMA,
        "before_snapshot_digest": before["snapshot_digest"],
        "after_snapshot_digest": after["snapshot_digest"],
        "unchanged_documents": 0,
        "changed_documents": len(changes),
        "changes": changes,
        "human_license_review_still_required": True,
        "dataset_retraining_performed": False,
        "production_jeeves_weights_updated": False,
    }
    result["unchanged_documents"] = len(previous.keys() & current.keys()) - sum(
        (row["sdk_id"], row["path"]) in previous and
        (row["sdk_id"], row["path"]) in current
        for row in changes
    )
    result["drift_digest"] = _digest(result)
    return result
