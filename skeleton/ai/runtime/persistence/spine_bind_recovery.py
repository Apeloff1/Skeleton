"""Recovery plan derived from a dark bind snapshot.

This is intentionally a non-activation object. It makes unresolved cutover
dependencies explicit and digest-bound instead of inferring readiness from file
presence or green local tests.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineBindRecoveryError(RuntimeError):
    """Bind recovery rejected its inputs. Not a maturity signal."""


_BLOCKERS = (
    "apply-not-landed",
    "provider-surface-unclaimed",
    "pr-automation-unclaimed",
    "ci-green-unread",
    "merge-unread",
    "motor-unwired",
    "dispatcher-unwired",
)


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class SpineBindRecovery:
    """Produce a recovery plan that cannot self-activate."""

    def plan(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(snapshot, dict) or snapshot.get("kind") != "spine_bind_snapshot":
            raise SpineBindRecoveryError("snapshot must be a spine_bind_snapshot")
        tenant_id = snapshot.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindRecoveryError("snapshot tenant missing")
        digest = snapshot.get("digest")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SpineBindRecoveryError("snapshot digest missing")
        for flag in (
            "provider_claimed",
            "pr_claimed",
            "gap_filled",
            "live_motor",
            "dispatcher_running",
            "ci_green",
            "merged",
            "apply_landed",
            "activated",
        ):
            if snapshot.get(flag) is not False:
                raise SpineBindRecoveryError("snapshot is not dark")

        body = {
            "kind": "spine_bind_recovery",
            "hit": False,
            "law": "recovery-plan-does-not-activate",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "snapshot_digest": digest,
            "ready": False,
            "activated": False,
            "blockers": list(_BLOCKERS),
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
