"""Fail-closed verifier for an anchored P2 bind restore receipt."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineBindRestoreVerifyError(RuntimeError):
    """Restore receipt verification rejected its input. Not a maturity signal."""


class SpineBindRestoreVerify:
    """Verify restore receipt integrity while preserving the dark boundary."""

    def verify(self, receipt: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(receipt, dict) or receipt.get("kind") != "spine_bind_restore_receipt":
            raise SpineBindRestoreVerifyError("receipt must be a spine_bind_restore_receipt")
        expected = receipt.get("digest")
        if not isinstance(expected, str) or len(expected) != 64:
            raise SpineBindRestoreVerifyError("receipt digest missing")
        actual = hashlib.sha256(
            json.dumps(
                {key: value for key, value in receipt.items() if key != "digest"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if expected != actual:
            raise SpineBindRestoreVerifyError("restore receipt digest mismatch")
        if receipt.get("restored") is not True or receipt.get("verified") is not True:
            raise SpineBindRestoreVerifyError("restore receipt is not verified")
        for field in (
            "backup_restore_digest",
            "recovery_digest",
            "chain_digest",
            "bundle_digest",
        ):
            value = receipt.get(field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or value.lower() != value
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise SpineBindRestoreVerifyError(f"{field} must be lowercase SHA-256 hex")
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
            if receipt.get(flag) is not False:
                raise SpineBindRestoreVerifyError("restore receipt is not dark")
        return {
            "kind": "spine_bind_restore_verify",
            "hit": True,
            "law": "restore-verification-does-not-activate",
            "citation": "VOL-134",
            "tenant_id": receipt.get("tenant_id"),
            "receipt_digest": expected,
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
