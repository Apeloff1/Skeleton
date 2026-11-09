"""Authenticated dual-control evidence for a future P2 cutover.

The core does not authenticate identities itself. A deployment-owned verifier is
injected for each approval receipt. Two distinct authenticated approvers from
separate authority domains must approve the exact candidate and rehearsal
digests inside a bounded validity window. Qualification is evidence only: it
does not select a driver or activate runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable


class SpineCutoverAuthorizationError(RuntimeError):
    """Dual-control evidence is invalid, stale, unauthenticated, or mis-scoped."""


_REQUIRED_DOMAINS = {"operations", "reliability"}


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SpineCutoverAuthorizationError(f"{field} must be canonical non-empty text")
    return value


def _instant(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise SpineCutoverAuthorizationError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SpineCutoverAuthorizationError(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpineCutoverAuthorizationError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


class SpineCutoverAuthorization:
    """Qualify externally authenticated two-person approval evidence."""

    def qualify(
        self,
        *,
        candidate: dict[str, Any],
        rehearsal: dict[str, Any],
        approvals: list[dict[str, Any]],
        authenticate: Callable[[dict[str, Any]], bool],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(candidate, dict)
            or candidate.get("kind") != "spine_runtime_selection_candidate"
        ):
            raise SpineCutoverAuthorizationError("runtime selection candidate is missing")
        candidate_digest = candidate.get("digest")
        if not isinstance(candidate_digest, str) or len(candidate_digest) != 64:
            raise SpineCutoverAuthorizationError("candidate digest is invalid")
        for flag in ("runtime_driver_selected", "selection_authorized", "runtime_activated"):
            if candidate.get(flag) is not False:
                raise SpineCutoverAuthorizationError("candidate already gained runtime authority")

        if (
            not isinstance(rehearsal, dict)
            or rehearsal.get("kind") != "spine_cutover_rehearsal"
            or rehearsal.get("rehearsed") is not True
            or rehearsal.get("switch_refused") is not True
            or rehearsal.get("switch_reason") != "switch-not-landed"
        ):
            raise SpineCutoverAuthorizationError("verified refused cutover rehearsal is required")
        rehearsal_digest = rehearsal.get("digest")
        if not isinstance(rehearsal_digest, str) or len(rehearsal_digest) != 64:
            raise SpineCutoverAuthorizationError("rehearsal digest is invalid")
        for flag in ("runtime_driver_selected", "selection_authorized", "runtime_activated"):
            if rehearsal.get(flag) is not False:
                raise SpineCutoverAuthorizationError("rehearsal already gained runtime authority")

        if not callable(authenticate):
            raise SpineCutoverAuthorizationError("approval authenticator must be callable")
        if not isinstance(approvals, list) or len(approvals) != 2:
            raise SpineCutoverAuthorizationError("exactly two approval receipts are required")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineCutoverAuthorizationError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)

        normalized: list[dict[str, Any]] = []
        approver_ids: set[str] = set()
        approval_ids: set[str] = set()
        domains: set[str] = set()

        for approval in approvals:
            if not isinstance(approval, dict):
                raise SpineCutoverAuthorizationError("approval receipt must be a card")
            approval_id = _text(approval.get("approval_id"), "approval_id")
            approver_id = _text(approval.get("approver_id"), "approver_id")
            domain = _text(approval.get("authority_domain"), "authority_domain")
            if domain not in _REQUIRED_DOMAINS:
                raise SpineCutoverAuthorizationError("approval authority domain is unsupported")
            if approval.get("decision") != "approve":
                raise SpineCutoverAuthorizationError("approval decision must be approve")
            if approval.get("candidate_digest") != candidate_digest:
                raise SpineCutoverAuthorizationError("approval candidate scope mismatch")
            if approval.get("rehearsal_digest") != rehearsal_digest:
                raise SpineCutoverAuthorizationError("approval rehearsal scope mismatch")

            issued_at = _instant(approval.get("issued_at"), "issued_at")
            expires_at = _instant(approval.get("expires_at"), "expires_at")
            if issued_at > instant:
                raise SpineCutoverAuthorizationError("approval is not yet valid")
            if expires_at <= instant or expires_at <= issued_at:
                raise SpineCutoverAuthorizationError("approval is expired or has invalid lifetime")
            if (expires_at - issued_at).total_seconds() > 1800:
                raise SpineCutoverAuthorizationError("approval lifetime exceeds 30 minutes")

            attestation_digest = approval.get("attestation_digest")
            if not isinstance(attestation_digest, str) or len(attestation_digest) != 64:
                raise SpineCutoverAuthorizationError("approval attestation digest is invalid")
            try:
                authenticated = authenticate(dict(approval))
            except Exception as exc:
                raise SpineCutoverAuthorizationError("approval authentication failed closed") from exc
            if authenticated is not True:
                raise SpineCutoverAuthorizationError("approval was not externally authenticated")

            approver_ids.add(approver_id)
            approval_ids.add(approval_id)
            domains.add(domain)
            normalized.append(
                {
                    "approval_id": approval_id,
                    "approver_id": approver_id,
                    "authority_domain": domain,
                    "decision": "approve",
                    "candidate_digest": candidate_digest,
                    "rehearsal_digest": rehearsal_digest,
                    "issued_at": issued_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "attestation_digest": attestation_digest,
                    "externally_authenticated": True,
                }
            )

        if len(approver_ids) != 2:
            raise SpineCutoverAuthorizationError("dual control requires two distinct approvers")
        if len(approval_ids) != 2:
            raise SpineCutoverAuthorizationError("approval receipt identities must be distinct")
        if domains != _REQUIRED_DOMAINS:
            raise SpineCutoverAuthorizationError("operations and reliability approvals are both required")

        normalized.sort(key=lambda row: (row["authority_domain"], row["approval_id"]))
        evidence = {
            "candidate_digest": candidate_digest,
            "rehearsal_digest": rehearsal_digest,
            "approvals": normalized,
            "approver_count": 2,
            "authority_domains": sorted(domains),
            "external_authentication_required": True,
            "dual_control_authenticated": True,
            "authorization_qualified": True,
            "authorization_effective": False,
            "runtime_driver_selected": False,
            "selection_authorized": False,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_cutover_authorization",
            "hit": False,
            "law": "authenticated-dual-control-is-not-runtime-activation",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
