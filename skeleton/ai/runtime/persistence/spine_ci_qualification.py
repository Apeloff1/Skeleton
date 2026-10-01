"""Externally authenticated exact-head CI qualification for the P2 spine."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

from skeleton.persistence.spine_ci_policy import (
    REQUIRED_CHECK_POLICY_DIGEST,
    REQUIRED_CHECKS,
)


class SpineCiQualificationError(RuntimeError):
    """Exact-head CI qualification failed closed."""


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


class SpineCiQualification:
    """Qualify one complete exact-head required-check catalog."""

    def qualify(
        self,
        *,
        receipt: dict[str, Any],
        expected_head_sha: str,
        authenticate: Callable[[dict[str, Any]], bool],
    ) -> dict[str, Any]:
        if (
            not isinstance(expected_head_sha, str)
            or _SHA_RE.fullmatch(expected_head_sha) is None
        ):
            raise SpineCiQualificationError("expected head SHA is invalid")
        if not callable(authenticate):
            raise SpineCiQualificationError("CI authenticator must be callable")
        if (
            not isinstance(receipt, dict)
            or receipt.get("kind") != "spine_ci_exact_head_receipt"
        ):
            raise SpineCiQualificationError("exact-head CI receipt is missing")
        if receipt.get("authority_domain") != "ci-exact-head":
            raise SpineCiQualificationError("CI authority domain changed")
        if receipt.get("head_sha") != expected_head_sha:
            raise SpineCiQualificationError("CI receipt is not exact-head")
        if receipt.get("catalog_complete") is not True:
            raise SpineCiQualificationError(
                "CI required-check catalog is incomplete"
            )

        for field in ("pending_count", "failing_count", "missing_count"):
            value = receipt.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SpineCiQualificationError(f"{field} is invalid")
            if value != 0:
                raise SpineCiQualificationError(
                    f"CI receipt has nonzero {field}"
                )

        policy_digest = receipt.get("required_check_policy_digest")
        attestation = receipt.get("attestation_digest")
        for field, value in (
            ("required check policy digest", policy_digest),
            ("CI attestation digest", attestation),
        ):
            if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
                raise SpineCiQualificationError(f"{field} is invalid")

        checks = receipt.get("checks")
        if not isinstance(checks, list) or not checks:
            raise SpineCiQualificationError("CI required checks are missing")
        normalized: list[dict[str, Any]] = []
        names: set[str] = set()
        for check in checks:
            if not isinstance(check, dict):
                raise SpineCiQualificationError(
                    "CI check evidence must be an object"
                )
            name = check.get("name")
            if not isinstance(name, str) or not name or len(name) > 160:
                raise SpineCiQualificationError("CI check name is invalid")
            if name in names:
                raise SpineCiQualificationError(
                    "CI required-check catalog contains duplicates"
                )
            names.add(name)
            if check.get("head_sha") != expected_head_sha:
                raise SpineCiQualificationError(
                    f"CI check is not exact-head: {name}"
                )
            if check.get("conclusion") != "success":
                raise SpineCiQualificationError(
                    f"CI check is not successful: {name}"
                )
            run_id = check.get("run_id")
            run_attempt = check.get("run_attempt")
            if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
                raise SpineCiQualificationError(
                    f"CI run id is invalid: {name}"
                )
            if (
                isinstance(run_attempt, bool)
                or not isinstance(run_attempt, int)
                or run_attempt < 1
            ):
                raise SpineCiQualificationError(
                    f"CI run attempt is invalid: {name}"
                )
            normalized.append(
                {
                    "name": name,
                    "head_sha": expected_head_sha,
                    "run_id": run_id,
                    "run_attempt": run_attempt,
                    "conclusion": "success",
                }
            )
        normalized.sort(key=lambda item: item["name"])
        required_names = list(REQUIRED_CHECKS)
        actual_names = [row["name"] for row in normalized]
        if actual_names != required_names:
            raise SpineCiQualificationError(
                "CI required-check catalog does not match policy"
            )

        expected_count = receipt.get("required_check_count")
        if (
            isinstance(expected_count, bool)
            or not isinstance(expected_count, int)
            or expected_count != len(REQUIRED_CHECKS)
            or expected_count != len(normalized)
        ):
            raise SpineCiQualificationError(
                "CI required-check count mismatch"
            )
        if policy_digest != REQUIRED_CHECK_POLICY_DIGEST:
            raise SpineCiQualificationError(
                "CI required-check policy digest mismatch"
            )
        try:
            authenticated = authenticate(dict(receipt))
        except Exception as exc:
            raise SpineCiQualificationError(
                "CI receipt authentication failed closed"
            ) from exc
        if authenticated is not True:
            raise SpineCiQualificationError(
                "CI receipt was not externally authenticated"
            )

        evidence = {
            "authority_domain": receipt["authority_domain"],
            "head_sha": expected_head_sha,
            "required_check_policy_digest": REQUIRED_CHECK_POLICY_DIGEST,
            "required_check_count": expected_count,
            "checks": normalized,
            "checks_digest": _digest(normalized),
            "check_names": actual_names,
            "attestation_digest": attestation,
            "catalog_complete": True,
            "pending_count": 0,
            "failing_count": 0,
            "missing_count": 0,
            "receipt_authenticated": True,
            "ci_green": True,
            "merge_authority": False,
        }
        return {
            "kind": "spine_ci_qualification",
            "hit": True,
            "law": "complete-exact-head-ci-is-not-merge-authority",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
