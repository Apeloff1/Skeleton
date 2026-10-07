"""Fail-closed verifier for a bind recovery checkpoint bundle."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineBindBundleVerifyError(RuntimeError):
    """Bundle verification rejected its inputs. Not a maturity signal."""


class SpineBindBundleVerify:
    """Verify bundle integrity while preserving the no-activation boundary."""

    def verify(self, bundle: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(bundle, dict) or bundle.get("kind") != "spine_bind_bundle":
            raise SpineBindBundleVerifyError("bundle must be a spine_bind_bundle")
        expected = bundle.get("digest")
        if not isinstance(expected, str) or len(expected) != 64:
            raise SpineBindBundleVerifyError("bundle digest missing")
        actual = hashlib.sha256(
            json.dumps(
                {key: value for key, value in bundle.items() if key != "digest"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if expected != actual:
            raise SpineBindBundleVerifyError("bundle digest mismatch")
        if bundle.get("foreign") != 0:
            raise SpineBindBundleVerifyError("bundle leaked a foreign checkpoint")
        if bundle.get("inserted_on_replay") is not False or bundle.get("rewritten") is not False:
            raise SpineBindBundleVerifyError("bundle records checkpoint mutation")
        for flag in (
            "activated",
            "apply_landed",
            "live_motor",
            "dispatcher_running",
            "ci_green",
            "merged",
        ):
            if bundle.get(flag) is not False:
                raise SpineBindBundleVerifyError("bundle is not dark")
        return {
            "kind": "spine_bind_bundle_verify",
            "hit": True,
            "law": "bundle-verification-does-not-activate",
            "citation": "VOL-134",
            "tenant_id": bundle.get("tenant_id"),
            "bundle_digest": expected,
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
