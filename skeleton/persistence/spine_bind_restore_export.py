"""Canonical portable export for P2 bind restore evidence.

The export is deterministic machine JSON. It binds the anchored restore receipt
and durable continuity card without granting runtime activation, maturity, merge,
or sign-off authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineBindRestoreExportError(RuntimeError):
    """Restore export rejected its inputs. Not a maturity signal."""


def _hex64(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise SpineBindRestoreExportError(f"{field} must be lowercase SHA-256 hex")
    return value


class SpineBindRestoreExport:
    """Serialize restore continuity into canonical, content-addressed JSON."""

    def card(
        self,
        *,
        receipt: dict[str, Any],
        continuity: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("kind") != "spine_bind_restore_receipt":
            raise SpineBindRestoreExportError("receipt kind mismatch")
        if not isinstance(continuity, dict) or continuity.get("kind") != "spine_bind_restore_continuity":
            raise SpineBindRestoreExportError("continuity kind mismatch")
        tenant_id = receipt.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindRestoreExportError("receipt tenant missing")
        if continuity.get("tenant_id") != tenant_id:
            raise SpineBindRestoreExportError("continuity tenant mismatch")
        receipt_digest = _hex64(receipt.get("digest"), "receipt.digest")
        if continuity.get("receipt_digest") != receipt_digest:
            raise SpineBindRestoreExportError("continuity receipt digest mismatch")
        continuity_digest = _hex64(continuity.get("digest"), "continuity.digest")
        backup_digest = _hex64(
            receipt.get("backup_restore_digest"),
            "backup_restore_digest",
        )
        recovery_digest = _hex64(receipt.get("recovery_digest"), "recovery_digest")
        journal_row_digest = _hex64(
            continuity.get("journal_row_digest"),
            "journal_row_digest",
        )
        chain_digest = _hex64(continuity.get("chain_digest"), "chain_digest")
        if continuity.get("durable") is not True:
            raise SpineBindRestoreExportError("continuity is not durable")
        if continuity.get("tenant_isolated") is not True:
            raise SpineBindRestoreExportError("continuity is not tenant isolated")
        if continuity.get("replay_safe") is not True:
            raise SpineBindRestoreExportError("continuity is not replay safe")
        for card in (receipt, continuity):
            for flag in (
                "activated",
                "apply_landed",
                "live_motor",
                "dispatcher_running",
                "provider_surface_green",
                "pr_automation_green",
                "ci_green",
                "merged",
            ):
                if card.get(flag) is not False:
                    raise SpineBindRestoreExportError("restore evidence is not dark")

        payload = {
            "schema_version": 1,
            "kind": "spine_bind_restore_evidence",
            "law": "portable-evidence-is-not-activation",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "receipt_digest": receipt_digest,
            "continuity_digest": continuity_digest,
            "backup_restore_digest": backup_digest,
            "recovery_digest": recovery_digest,
            "journal_row_digest": journal_row_digest,
            "restore_chain_digest": chain_digest,
            "durable": True,
            "tenant_isolated": True,
            "replay_safe": True,
            "activated": False,
            "apply_landed": False,
            "live_motor": False,
            "dispatcher_running": False,
            "provider_surface_green": False,
            "pr_automation_green": False,
            "ci_green": False,
            "merged": False,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return {
            "kind": "spine_bind_restore_export",
            "hit": True,
            "law": "portable-evidence-is-not-activation",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "export_json": encoded,
            "digest": digest,
            "bytes": len(encoded.encode("utf-8")),
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
