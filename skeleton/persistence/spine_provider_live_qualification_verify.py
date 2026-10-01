"""Independent verifier for P2 live-provider qualification."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


class SpineProviderLiveQualificationVerifyError(RuntimeError):
    """Live-provider qualification verification failed closed."""


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


class SpineProviderLiveQualificationVerify:
    """Verify live provider evidence without granting merge authority."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if (
            not isinstance(card, dict)
            or card.get("kind") != "spine_provider_live_qualification"
        ):
            raise SpineProviderLiveQualificationVerifyError(
                "provider live qualification kind mismatch"
            )
        head_sha = card.get("head_sha")
        if not isinstance(head_sha, str) or _SHA_RE.fullmatch(head_sha) is None:
            raise SpineProviderLiveQualificationVerifyError(
                "provider live head SHA is invalid"
            )
        for field in (
            "closure_digest",
            "request_digest",
            "response_digest",
            "architecture_digest",
        ):
            value = card.get(field)
            if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
                raise SpineProviderLiveQualificationVerifyError(
                    f"{field} is invalid"
                )
        for field in (
            "provider_id",
            "provider_family",
            "model",
            "operation_id",
            "request_id",
            "response_id",
            "issued_at",
            "valid_until",
        ):
            value = card.get(field)
            if not isinstance(value, str) or not value:
                raise SpineProviderLiveQualificationVerifyError(
                    f"{field} is missing"
                )
        if card.get("provider_family") != "runtime_model":
            raise SpineProviderLiveQualificationVerifyError(
                "provider family changed"
            )
        latency_ms = card.get("latency_ms")
        if (
            isinstance(latency_ms, bool)
            or not isinstance(latency_ms, int)
            or latency_ms < 0
            or latency_ms > 300_000
        ):
            raise SpineProviderLiveQualificationVerifyError(
                "provider live latency is invalid"
            )
        for field in (
            "receipt_authenticated",
            "provider_surface_closure_green",
            "provider_surface_live_green",
            "provider_surface_green",
        ):
            if card.get(field) is not True:
                raise SpineProviderLiveQualificationVerifyError(
                    f"provider live invariant missing: {field}"
                )
        if card.get("pr_automation_green") is not False:
            raise SpineProviderLiveQualificationVerifyError(
                "provider live qualification overclaimed PR automation"
            )
        if card.get("merge_authority") is not False:
            raise SpineProviderLiveQualificationVerifyError(
                "provider live qualification overclaimed merge authority"
            )

        evidence = {
            "head_sha": head_sha,
            "closure_digest": card["closure_digest"],
            "provider_id": card["provider_id"],
            "provider_family": card["provider_family"],
            "model": card["model"],
            "operation_id": card["operation_id"],
            "request_id": card["request_id"],
            "response_id": card["response_id"],
            "request_digest": card["request_digest"],
            "response_digest": card["response_digest"],
            "architecture_digest": card["architecture_digest"],
            "latency_ms": latency_ms,
            "issued_at": card["issued_at"],
            "valid_until": card["valid_until"],
            "receipt_authenticated": card["receipt_authenticated"],
            "provider_surface_closure_green": card[
                "provider_surface_closure_green"
            ],
            "provider_surface_live_green": card[
                "provider_surface_live_green"
            ],
            "provider_surface_green": card["provider_surface_green"],
            "pr_automation_green": card["pr_automation_green"],
            "merge_authority": card["merge_authority"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineProviderLiveQualificationVerifyError(
                "provider live qualification digest mismatch"
            )
        return {
            "kind": "spine_provider_live_qualification_verify",
            "hit": True,
            "law": "live-provider-verification-does-not-grant-merge-authority",
            "citation": "VOL-134",
            "head_sha": head_sha,
            "qualification_digest": digest,
            "verified": True,
            "provider_surface_closure_green": True,
            "provider_surface_live_green": True,
            "provider_surface_green": True,
            "pr_automation_green": False,
            "merge_authority": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
