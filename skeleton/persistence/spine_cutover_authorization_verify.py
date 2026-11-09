"""Independent structural verifier for P2 dual-control authorization evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineCutoverAuthorizationVerifyError(RuntimeError):
    """Authorization evidence verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineCutoverAuthorizationVerify:
    """Verify qualified dual-control evidence without making it effective."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_cutover_authorization":
            raise SpineCutoverAuthorizationVerifyError("authorization kind mismatch")
        if card.get("dual_control_authenticated") is not True:
            raise SpineCutoverAuthorizationVerifyError("dual control is not authenticated")
        if card.get("authorization_qualified") is not True:
            raise SpineCutoverAuthorizationVerifyError("authorization evidence is not qualified")
        if card.get("external_authentication_required") is not True:
            raise SpineCutoverAuthorizationVerifyError("external authentication boundary changed")
        if card.get("authorization_effective") is not False:
            raise SpineCutoverAuthorizationVerifyError("authorization became effective inside verifier")
        for flag in ("runtime_driver_selected", "selection_authorized", "runtime_activated"):
            if card.get(flag) is not False:
                raise SpineCutoverAuthorizationVerifyError("authorization evidence gained runtime authority")

        approvals = card.get("approvals")
        if not isinstance(approvals, list) or len(approvals) != 2:
            raise SpineCutoverAuthorizationVerifyError("authorization approval cardinality changed")
        domains = [row.get("authority_domain") for row in approvals if isinstance(row, dict)]
        approvers = [row.get("approver_id") for row in approvals if isinstance(row, dict)]
        approval_ids = [row.get("approval_id") for row in approvals if isinstance(row, dict)]
        if set(domains) != {"operations", "reliability"}:
            raise SpineCutoverAuthorizationVerifyError("authorization domains changed")
        if len(set(approvers)) != 2 or len(set(approval_ids)) != 2:
            raise SpineCutoverAuthorizationVerifyError("authorization dual-control identity collapsed")
        if any(row.get("externally_authenticated") is not True for row in approvals):
            raise SpineCutoverAuthorizationVerifyError("approval authentication evidence missing")

        candidate_digest = card.get("candidate_digest")
        rehearsal_digest = card.get("rehearsal_digest")
        if not isinstance(candidate_digest, str) or len(candidate_digest) != 64:
            raise SpineCutoverAuthorizationVerifyError("candidate digest is invalid")
        if not isinstance(rehearsal_digest, str) or len(rehearsal_digest) != 64:
            raise SpineCutoverAuthorizationVerifyError("rehearsal digest is invalid")
        for row in approvals:
            if row.get("candidate_digest") != candidate_digest:
                raise SpineCutoverAuthorizationVerifyError("approval candidate scope mismatch")
            if row.get("rehearsal_digest") != rehearsal_digest:
                raise SpineCutoverAuthorizationVerifyError("approval rehearsal scope mismatch")
            attestation = row.get("attestation_digest")
            if not isinstance(attestation, str) or len(attestation) != 64:
                raise SpineCutoverAuthorizationVerifyError("approval attestation digest is invalid")

        normalized = sorted(
            [dict(row) for row in approvals],
            key=lambda row: (row["authority_domain"], row["approval_id"]),
        )
        evidence = {
            "candidate_digest": candidate_digest,
            "rehearsal_digest": rehearsal_digest,
            "approvals": normalized,
            "approver_count": card.get("approver_count"),
            "authority_domains": card.get("authority_domains"),
            "external_authentication_required": card.get("external_authentication_required"),
            "dual_control_authenticated": card.get("dual_control_authenticated"),
            "authorization_qualified": card.get("authorization_qualified"),
            "authorization_effective": card.get("authorization_effective"),
            "runtime_driver_selected": card.get("runtime_driver_selected"),
            "selection_authorized": card.get("selection_authorized"),
            "runtime_activated": card.get("runtime_activated"),
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineCutoverAuthorizationVerifyError("authorization digest mismatch")

        return {
            "kind": "spine_cutover_authorization_verify",
            "hit": False,
            "law": "authorization-verification-does-not-make-authorization-effective",
            "citation": "VOL-134",
            "authorization_digest": digest,
            "verified": True,
            "dual_control_authenticated": True,
            "authorization_qualified": True,
            "authorization_effective": False,
            "runtime_driver_selected": False,
            "selection_authorized": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
