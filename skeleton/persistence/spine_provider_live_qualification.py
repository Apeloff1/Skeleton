"""Externally authenticated live-provider qualification for the P2 spine."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Callable

from skeleton.persistence.spine_provider_surface_qualification_verify import (
    SpineProviderSurfaceQualificationVerify,
)


class SpineProviderLiveQualificationError(RuntimeError):
    """Live-provider qualification failed closed."""


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _instant(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise SpineProviderLiveQualificationError(
            f"{field} must be ISO-8601 text"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SpineProviderLiveQualificationError(
            f"{field} is not valid ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpineProviderLiveQualificationError(
            f"{field} must be timezone-aware"
        )
    return parsed.astimezone(timezone.utc)


class SpineProviderLiveQualification:
    """Bind exact-head closure to one authenticated provider-call receipt."""

    def qualify(
        self,
        *,
        closure: dict[str, Any],
        closure_verify: dict[str, Any],
        receipt: dict[str, Any],
        expected_head_sha: str,
        authenticate: Callable[[dict[str, Any]], bool],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(expected_head_sha, str)
            or _SHA_RE.fullmatch(expected_head_sha) is None
        ):
            raise SpineProviderLiveQualificationError(
                "expected head SHA is invalid"
            )
        if (
            not isinstance(closure, dict)
            or closure.get("kind") != "spine_provider_surface_qualification"
            or closure.get("head_sha") != expected_head_sha
            or closure.get("exact_head") is not True
            or closure.get("independent_agreement") is not True
            or closure.get("provider_surface_closure_green") is not True
            or closure.get("provider_surface_live_green") is not False
            or closure.get("provider_surface_green") is not False
        ):
            raise SpineProviderLiveQualificationError(
                "exact-head provider closure qualification is required"
            )
        closure_digest = closure.get("digest")
        if (
            not isinstance(closure_digest, str)
            or _DIGEST_RE.fullmatch(closure_digest) is None
        ):
            raise SpineProviderLiveQualificationError(
                "provider closure digest is invalid"
            )
        try:
            current_closure_verify = (
                SpineProviderSurfaceQualificationVerify().verify(closure)
            )
        except Exception as exc:
            raise SpineProviderLiveQualificationError(
                "current provider closure verification failed closed"
            ) from exc
        if current_closure_verify.get("qualification_digest") != closure_digest:
            raise SpineProviderLiveQualificationError(
                "current provider closure digest changed"
            )
        if (
            not isinstance(closure_verify, dict)
            or closure_verify.get("kind")
            != "spine_provider_surface_qualification_verify"
            or closure_verify.get("verified") is not True
            or closure_verify.get("head_sha") != expected_head_sha
            or closure_verify.get("qualification_digest") != closure_digest
            or closure_verify.get("provider_surface_closure_green") is not True
            or closure_verify.get("provider_surface_live_green") is not False
            or closure_verify.get("provider_surface_green") is not False
        ):
            raise SpineProviderLiveQualificationError(
                "independent provider closure verification is required"
            )
        if not callable(authenticate):
            raise SpineProviderLiveQualificationError(
                "provider live authenticator must be callable"
            )
        if (
            not isinstance(receipt, dict)
            or receipt.get("kind") != "spine_provider_live_receipt"
        ):
            raise SpineProviderLiveQualificationError(
                "provider live receipt is missing"
            )
        if receipt.get("authority_domain") != "provider-live":
            raise SpineProviderLiveQualificationError(
                "provider live authority domain changed"
            )
        if receipt.get("decision") != "qualify-live-provider":
            raise SpineProviderLiveQualificationError(
                "provider live decision is invalid"
            )
        if receipt.get("head_sha") != expected_head_sha:
            raise SpineProviderLiveQualificationError(
                "provider live receipt is not exact-head"
            )
        if receipt.get("closure_digest") != closure_digest:
            raise SpineProviderLiveQualificationError(
                "provider live closure scope mismatch"
            )
        if receipt.get("provider_family") != "runtime_model":
            raise SpineProviderLiveQualificationError(
                "provider live family changed"
            )
        if receipt.get("success") is not True:
            raise SpineProviderLiveQualificationError(
                "provider live request did not succeed"
            )
        if receipt.get("network_transport_used") is not True:
            raise SpineProviderLiveQualificationError(
                "provider live request did not use provider transport"
            )
        if receipt.get("credential_boundary_used") is not True:
            raise SpineProviderLiveQualificationError(
                "provider live credential boundary was not used"
            )
        if receipt.get("architecture_acknowledged") is not True:
            raise SpineProviderLiveQualificationError(
                "provider architecture acknowledgement is missing"
            )

        for field in (
            "provider_id",
            "model",
            "operation_id",
            "request_id",
            "response_id",
        ):
            value = receipt.get(field)
            if not isinstance(value, str) or not value or len(value) > 256:
                raise SpineProviderLiveQualificationError(
                    f"{field} is invalid"
                )
        for field in (
            "request_digest",
            "response_digest",
            "architecture_digest",
            "attestation_digest",
        ):
            value = receipt.get(field)
            if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
                raise SpineProviderLiveQualificationError(
                    f"{field} is invalid"
                )
        latency_ms = receipt.get("latency_ms")
        if (
            isinstance(latency_ms, bool)
            or not isinstance(latency_ms, int)
            or latency_ms < 0
            or latency_ms > 300_000
        ):
            raise SpineProviderLiveQualificationError(
                "provider live latency is invalid"
            )

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineProviderLiveQualificationError(
                "now must be timezone-aware"
            )
        instant = instant.astimezone(timezone.utc)
        issued_at = _instant(receipt.get("issued_at"), "issued_at")
        expires_at = _instant(receipt.get("expires_at"), "expires_at")
        if issued_at > instant:
            raise SpineProviderLiveQualificationError(
                "provider live receipt is not yet valid"
            )
        if expires_at <= instant or expires_at <= issued_at:
            raise SpineProviderLiveQualificationError(
                "provider live receipt is expired or invalid"
            )
        if (expires_at - issued_at).total_seconds() > 300:
            raise SpineProviderLiveQualificationError(
                "provider live receipt lifetime exceeds five minutes"
            )
        try:
            authenticated = authenticate(dict(receipt))
        except Exception as exc:
            raise SpineProviderLiveQualificationError(
                "provider live receipt authentication failed closed"
            ) from exc
        if authenticated is not True:
            raise SpineProviderLiveQualificationError(
                "provider live receipt was not externally authenticated"
            )

        evidence = {
            "authority_domain": receipt["authority_domain"],
            "decision": receipt["decision"],
            "success": receipt["success"],
            "network_transport_used": receipt["network_transport_used"],
            "credential_boundary_used": receipt["credential_boundary_used"],
            "architecture_acknowledged": receipt[
                "architecture_acknowledged"
            ],
            "head_sha": expected_head_sha,
            "closure_digest": closure_digest,
            "provider_id": receipt["provider_id"],
            "provider_family": receipt["provider_family"],
            "model": receipt["model"],
            "operation_id": receipt["operation_id"],
            "request_id": receipt["request_id"],
            "response_id": receipt["response_id"],
            "request_digest": receipt["request_digest"],
            "response_digest": receipt["response_digest"],
            "architecture_digest": receipt["architecture_digest"],
            "attestation_digest": receipt["attestation_digest"],
            "latency_ms": latency_ms,
            "issued_at": issued_at.isoformat(),
            "valid_until": expires_at.isoformat(),
            "receipt_authenticated": True,
            "provider_surface_closure_green": True,
            "provider_surface_live_green": True,
            "provider_surface_green": True,
            "pr_automation_green": False,
            "merge_authority": False,
        }
        return {
            "kind": "spine_provider_live_qualification",
            "hit": True,
            "law": "exact-head-closure-plus-live-call-qualifies-provider-surface",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
