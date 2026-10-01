"""Independent verifier for P2 exact-head CI qualification."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


class SpineCiQualificationVerifyError(RuntimeError):
    """Exact-head CI qualification verification failed closed."""


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


class SpineCiQualificationVerify:
    """Verify CI-green evidence without granting merge authority."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if (
            not isinstance(card, dict)
            or card.get("kind") != "spine_ci_qualification"
        ):
            raise SpineCiQualificationVerifyError(
                "CI qualification kind mismatch"
            )
        head_sha = card.get("head_sha")
        if not isinstance(head_sha, str) or _SHA_RE.fullmatch(head_sha) is None:
            raise SpineCiQualificationVerifyError(
                "CI qualification head SHA is invalid"
            )
        for field in ("required_check_policy_digest", "checks_digest"):
            value = card.get(field)
            if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
                raise SpineCiQualificationVerifyError(f"{field} is invalid")
        count = card.get("required_check_count")
        names = card.get("check_names")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise SpineCiQualificationVerifyError(
                "CI required-check count is invalid"
            )
        if (
            not isinstance(names, list)
            or len(names) != count
            or len(set(names)) != count
            or names != sorted(names)
            or not all(isinstance(name, str) and name for name in names)
        ):
            raise SpineCiQualificationVerifyError(
                "CI check-name catalog is invalid"
            )
        for field in ("catalog_complete", "receipt_authenticated", "ci_green"):
            if card.get(field) is not True:
                raise SpineCiQualificationVerifyError(
                    f"CI invariant missing: {field}"
                )
        for field in ("pending_count", "failing_count", "missing_count"):
            if card.get(field) != 0:
                raise SpineCiQualificationVerifyError(
                    f"CI non-green count is nonzero: {field}"
                )
        if card.get("merge_authority") is not False:
            raise SpineCiQualificationVerifyError(
                "CI qualification overclaimed merge authority"
            )
        evidence = {
            "head_sha": head_sha,
            "required_check_policy_digest": card[
                "required_check_policy_digest"
            ],
            "required_check_count": count,
            "checks_digest": card["checks_digest"],
            "check_names": list(names),
            "catalog_complete": card["catalog_complete"],
            "pending_count": card["pending_count"],
            "failing_count": card["failing_count"],
            "missing_count": card["missing_count"],
            "receipt_authenticated": card["receipt_authenticated"],
            "ci_green": card["ci_green"],
            "merge_authority": card["merge_authority"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineCiQualificationVerifyError(
                "CI qualification digest mismatch"
            )
        return {
            "kind": "spine_ci_qualification_verify",
            "hit": True,
            "law": "CI-verification-does-not-grant-merge-authority",
            "citation": "VOL-134",
            "head_sha": head_sha,
            "qualification_digest": digest,
            "verified": True,
            "ci_green": True,
            "merge_authority": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
