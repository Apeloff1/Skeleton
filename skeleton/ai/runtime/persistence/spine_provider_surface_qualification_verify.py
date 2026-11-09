"""Independent verifier for paired provider-surface closure evidence."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


class SpineProviderSurfaceQualificationVerifyError(RuntimeError):
    """Provider-surface closure verification failed closed."""


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineProviderSurfaceQualificationVerify:
    """Verify closure-green evidence without promoting live provider health."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if (
            not isinstance(card, dict)
            or card.get("kind") != "spine_provider_surface_qualification"
        ):
            raise SpineProviderSurfaceQualificationVerifyError(
                "provider qualification kind mismatch"
            )
        head_sha = card.get("head_sha")
        if not isinstance(head_sha, str) or _SHA_RE.fullmatch(head_sha) is None:
            raise SpineProviderSurfaceQualificationVerifyError(
                "provider qualification head is invalid"
            )
        for field in (
            "canonical_receipt_digest",
            "independent_receipt_digest",
            "declared_digest",
            "independent_declared_surface_digest",
            "discovered_digest",
        ):
            value = card.get(field)
            if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
                raise SpineProviderSurfaceQualificationVerifyError(
                    f"{field} is invalid"
                )
        for field in ("declared_count", "discovered_count", "scanned_python_files"):
            value = card.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SpineProviderSurfaceQualificationVerifyError(
                    f"{field} is invalid"
                )
        for field in (
            "exact_head",
            "independent_agreement",
            "provider_surface_closure_green",
        ):
            if card.get(field) is not True:
                raise SpineProviderSurfaceQualificationVerifyError(
                    f"provider closure invariant missing: {field}"
                )
        for field in (
            "provider_surface_live_green",
            "provider_surface_green",
            "pr_automation_green",
        ):
            if card.get(field) is not False:
                raise SpineProviderSurfaceQualificationVerifyError(
                    f"provider closure overclaimed: {field}"
                )

        evidence = {
            "head_sha": head_sha,
            "canonical_receipt_digest": card["canonical_receipt_digest"],
            "independent_receipt_digest": card[
                "independent_receipt_digest"
            ],
            "declared_digest": card["declared_digest"],
            "independent_declared_surface_digest": card[
                "independent_declared_surface_digest"
            ],
            "discovered_digest": card["discovered_digest"],
            "declared_count": card["declared_count"],
            "discovered_count": card["discovered_count"],
            "scanned_python_files": card["scanned_python_files"],
            "exact_head": card["exact_head"],
            "independent_agreement": card["independent_agreement"],
            "provider_surface_closure_green": card[
                "provider_surface_closure_green"
            ],
            "provider_surface_live_green": card[
                "provider_surface_live_green"
            ],
            "provider_surface_green": card["provider_surface_green"],
            "pr_automation_green": card["pr_automation_green"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineProviderSurfaceQualificationVerifyError(
                "provider qualification digest mismatch"
            )
        return {
            "kind": "spine_provider_surface_qualification_verify",
            "hit": True,
            "law": "provider-closure-verification-does-not-claim-live-health",
            "citation": "VOL-134",
            "head_sha": head_sha,
            "qualification_digest": digest,
            "verified": True,
            "provider_surface_closure_green": True,
            "provider_surface_live_green": False,
            "provider_surface_green": False,
            "pr_automation_green": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
