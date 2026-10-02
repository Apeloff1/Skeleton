"""Anchored receipt for a restored P2 bind checkpoint authority.

The receipt binds the pre-destroy backup digest and expected recovery digest to
the restored checkpoint evidence. It is tamper-evident evidence, not a digital
signature and not runtime activation authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineBindRestoreReceiptError(RuntimeError):
    """Restore receipt rejected its inputs. Not a maturity signal."""


def _hex64(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise SpineBindRestoreReceiptError(f"{field} must be lowercase SHA-256 hex")
    return value


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class SpineBindRestoreReceipt:
    """Bind restored dark evidence to the backup and expected recovery digest."""

    def card(
        self,
        *,
        backup_digest: str,
        restore_digest: str,
        expected_recovery_digest: str,
        checkpoint: dict[str, Any],
        replay: dict[str, Any],
        tenant: dict[str, Any],
        chain: dict[str, Any],
        bundle: dict[str, Any],
        verified: dict[str, Any],
    ) -> dict[str, Any]:
        backup_digest = _hex64(backup_digest, "backup_digest")
        restore_digest = _hex64(restore_digest, "restore_digest")
        expected_recovery_digest = _hex64(
            expected_recovery_digest,
            "expected_recovery_digest",
        )
        if backup_digest != restore_digest:
            raise SpineBindRestoreReceiptError("backup and restore digests differ")

        if not isinstance(checkpoint, dict) or checkpoint.get("kind") != "spine_bind_checkpoint":
            raise SpineBindRestoreReceiptError("checkpoint kind mismatch")
        tenant_id = checkpoint.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindRestoreReceiptError("checkpoint tenant missing")
        if checkpoint.get("seen") is not True:
            raise SpineBindRestoreReceiptError("restored checkpoint was not seen")
        if checkpoint.get("recovery_digest") != expected_recovery_digest:
            raise SpineBindRestoreReceiptError("restored recovery digest changed")
        if checkpoint.get("activated") is not False:
            raise SpineBindRestoreReceiptError("restored checkpoint activated")

        if not isinstance(replay, dict) or replay.get("kind") != "spine_bind_checkpoint_replay":
            raise SpineBindRestoreReceiptError("replay kind mismatch")
        if replay.get("tenant_id") != tenant_id:
            raise SpineBindRestoreReceiptError("replay tenant mismatch")
        if replay.get("recovery_digest") != expected_recovery_digest:
            raise SpineBindRestoreReceiptError("replay recovery digest changed")
        if replay.get("inserted") is not False or replay.get("rewritten") is not False:
            raise SpineBindRestoreReceiptError("replay mutated checkpoint")
        if replay.get("rows_before") != replay.get("rows_after"):
            raise SpineBindRestoreReceiptError("replay row count changed")
        if replay.get("activated") is not False:
            raise SpineBindRestoreReceiptError("replay activated")

        if not isinstance(tenant, dict) or tenant.get("kind") != "spine_bind_checkpoint_tenant":
            raise SpineBindRestoreReceiptError("tenant card kind mismatch")
        if tenant.get("tenant_id") != tenant_id:
            raise SpineBindRestoreReceiptError("tenant card mismatch")
        if tenant.get("foreign") != 0:
            raise SpineBindRestoreReceiptError("foreign checkpoint visible")
        if expected_recovery_digest not in tenant.get("digests", []):
            raise SpineBindRestoreReceiptError("tenant view lost recovery digest")
        count = tenant.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise SpineBindRestoreReceiptError("tenant checkpoint count invalid")
        if tenant.get("activated") is not False:
            raise SpineBindRestoreReceiptError("tenant card activated")

        if not isinstance(chain, dict) or chain.get("kind") != "spine_bind_checkpoint_chain":
            raise SpineBindRestoreReceiptError("chain kind mismatch")
        if chain.get("tenant_id") != tenant_id:
            raise SpineBindRestoreReceiptError("chain tenant mismatch")
        if chain.get("rows") != count:
            raise SpineBindRestoreReceiptError("chain row count differs from tenant view")
        if chain.get("rewritten") is not False or chain.get("activated") is not False:
            raise SpineBindRestoreReceiptError("checkpoint chain mutated or activated")
        chain_digest = _hex64(chain.get("digest"), "chain.digest")

        if not isinstance(bundle, dict) or bundle.get("kind") != "spine_bind_bundle":
            raise SpineBindRestoreReceiptError("bundle kind mismatch")
        if bundle.get("tenant_id") != tenant_id:
            raise SpineBindRestoreReceiptError("bundle tenant mismatch")
        if bundle.get("recovery_digest") != expected_recovery_digest:
            raise SpineBindRestoreReceiptError("bundle recovery digest changed")
        bundle_digest = _hex64(bundle.get("digest"), "bundle.digest")
        if bundle.get("activated") is not False:
            raise SpineBindRestoreReceiptError("bundle activated")

        if not isinstance(verified, dict) or verified.get("kind") != "spine_bind_bundle_verify":
            raise SpineBindRestoreReceiptError("bundle verification kind mismatch")
        if verified.get("tenant_id") != tenant_id:
            raise SpineBindRestoreReceiptError("bundle verification tenant mismatch")
        if verified.get("verified") is not True:
            raise SpineBindRestoreReceiptError("bundle was not verified")
        if verified.get("bundle_digest") != bundle_digest:
            raise SpineBindRestoreReceiptError("bundle verification digest mismatch")
        if verified.get("activated") is not False:
            raise SpineBindRestoreReceiptError("bundle verification activated")

        body = {
            "kind": "spine_bind_restore_receipt",
            "hit": True,
            "law": "restore-receipt-is-not-activation",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "backup_restore_digest": backup_digest,
            "recovery_digest": expected_recovery_digest,
            "checkpoint_rows": count,
            "chain_digest": chain_digest,
            "bundle_digest": bundle_digest,
            "restored": True,
            "verified": True,
            "activated": False,
            "apply_landed": False,
            "live_motor": False,
            "dispatcher_running": False,
            "provider_surface_green": False,
            "pr_automation_green": False,
            "ci_green": False,
            "merged": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
        body["digest"] = _digest(body)
        return body
