"""Digest of a spine read.

The digest is a SHA-256 of the card fields. It does not dispatch and it does
not sign work off.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.persistence.spine_drift import SpineDrift
from skeleton.persistence.spine_gap import SpineGap


class SpineDigestError(RuntimeError):
    """Digest rejected its inputs. Not a maturity signal."""


class SpineDigest:
    """Hash gap and drift for one operation."""

    def __init__(self, gap: SpineGap, drift: SpineDrift) -> None:
        if not isinstance(gap, SpineGap):
            raise SpineDigestError("gap must be a SpineGap")
        if not isinstance(drift, SpineDrift):
            raise SpineDigestError("drift must be a SpineDrift")
        self.gap = gap
        self.drift = drift

    def read(self, *, tenant_id: str, operation_id: str) -> dict[str, Any]:
        gap = self.gap.read(operation_id=operation_id)
        drift = self.drift.read(tenant_id=tenant_id, resource_id=f"op:{operation_id}")
        payload = {
            "gap_hit": gap["hit"],
            "missing": gap.get("missing", []),
            "sqlite_epoch": drift["sqlite_epoch"],
            "mongo_epoch": drift["mongo_epoch"],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return {
            "kind": "spine_digest",
            "hit": gap["hit"] and drift["hit"],
            "law": "sha256-gap-drift",
            "citation": "VOL-134",
            "digest": digest,
            "sqlite_epoch": drift["sqlite_epoch"],
            "mongo_epoch": drift["mongo_epoch"],
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
