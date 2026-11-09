"""Strict verifier for canonical portable P2 bind restore evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineBindRestoreExportVerifyError(RuntimeError):
    """Portable restore evidence failed strict verification."""


def _strict_json_object(raw: object) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise SpineBindRestoreExportVerifyError("export_json must be text")

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite JSON constant: {value}")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw,
            parse_constant=reject_constant,
            object_pairs_hook=unique_pairs,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SpineBindRestoreExportVerifyError("export JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise SpineBindRestoreExportVerifyError("export JSON must be an object")
    return payload


class SpineBindRestoreExportVerify:
    """Verify canonical encoding, digest, schema, and dark authority fields."""

    def verify(self, export: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(export, dict) or export.get("kind") != "spine_bind_restore_export":
            raise SpineBindRestoreExportVerifyError("export kind mismatch")
        raw = export.get("export_json")
        payload = _strict_json_object(raw)
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        if raw != canonical:
            raise SpineBindRestoreExportVerifyError("export JSON is not canonical")
        expected = export.get("digest")
        if not isinstance(expected, str) or len(expected) != 64:
            raise SpineBindRestoreExportVerifyError("export digest missing")
        actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if expected != actual:
            raise SpineBindRestoreExportVerifyError("export digest mismatch")
        if payload.get("schema_version") != 1:
            raise SpineBindRestoreExportVerifyError("unsupported export schema")
        if payload.get("kind") != "spine_bind_restore_evidence":
            raise SpineBindRestoreExportVerifyError("export payload kind mismatch")
        if payload.get("law") != "portable-evidence-is-not-activation":
            raise SpineBindRestoreExportVerifyError("export law mismatch")
        if payload.get("tenant_id") != export.get("tenant_id"):
            raise SpineBindRestoreExportVerifyError("export tenant mismatch")
        for field in (
            "receipt_digest",
            "continuity_digest",
            "backup_restore_digest",
            "recovery_digest",
            "journal_row_digest",
            "restore_chain_digest",
        ):
            value = payload.get(field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or value.lower() != value
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise SpineBindRestoreExportVerifyError(f"{field} must be lowercase SHA-256 hex")
        for flag in ("durable", "tenant_isolated", "replay_safe"):
            if payload.get(flag) is not True:
                raise SpineBindRestoreExportVerifyError("export evidence is incomplete")
        for flag in (
            "activated",
            "apply_landed",
            "live_motor",
            "dispatcher_running",
            "provider_surface_green",
            "pr_automation_green",
            "ci_green",
            "merged",
            "completion_checkbox",
            "implementation_signature",
            "verification_signature",
        ):
            if payload.get(flag) is not False:
                raise SpineBindRestoreExportVerifyError("export evidence gained authority")
        return {
            "kind": "spine_bind_restore_export_verify",
            "hit": True,
            "law": "portable-evidence-verification-does-not-activate",
            "citation": "VOL-134",
            "tenant_id": payload["tenant_id"],
            "export_digest": expected,
            "verified": True,
            "activated": False,
            "apply_landed": False,
            "live_motor": False,
            "dispatcher_running": False,
            "ci_green": False,
            "merged": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
