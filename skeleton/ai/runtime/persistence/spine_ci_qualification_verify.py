"""Independent verifier for P2 exact-head CI qualification."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from skeleton.persistence.spine_ci_policy import (
    CI_PRODUCER_EVENT,
    CI_PRODUCER_STATUS,
    CI_PRODUCER_WORKFLOW_NAME,
    CI_PRODUCER_WORKFLOW_PATH,
    REQUIRED_CHECK_EVENT,
    REQUIRED_CHECK_POLICY_DIGEST,
    REQUIRED_CHECKS,
    REQUIRED_CHECK_WORKFLOWS,
)


class SpineCiQualificationVerifyError(RuntimeError):
    """Exact-head CI qualification verification failed closed."""


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$"
)


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
        if card.get("authority_domain") != "ci-exact-head":
            raise SpineCiQualificationVerifyError(
                "CI authority domain changed"
            )
        repository = card.get("repository")
        if (
            not isinstance(repository, str)
            or _REPOSITORY_RE.fullmatch(repository) is None
            or card.get("producer_head_repository") != repository
        ):
            raise SpineCiQualificationVerifyError(
                "CI producer repository changed"
            )
        if card.get("producer_workflow_name") != CI_PRODUCER_WORKFLOW_NAME:
            raise SpineCiQualificationVerifyError(
                "CI producer workflow name changed"
            )
        if card.get("producer_workflow_path") != CI_PRODUCER_WORKFLOW_PATH:
            raise SpineCiQualificationVerifyError(
                "CI producer workflow path changed"
            )
        if card.get("producer_event") != CI_PRODUCER_EVENT:
            raise SpineCiQualificationVerifyError(
                "CI producer event changed"
            )
        if card.get("producer_status") != CI_PRODUCER_STATUS:
            raise SpineCiQualificationVerifyError(
                "CI producer status changed"
            )
        for field in (
            "producer_workflow_id",
            "producer_run_id",
            "producer_run_attempt",
        ):
            value = card.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SpineCiQualificationVerifyError(
                    f"{field} is invalid"
                )
        producer_head_branch = card.get("producer_head_branch")
        if (
            not isinstance(producer_head_branch, str)
            or not producer_head_branch.strip()
        ):
            raise SpineCiQualificationVerifyError(
                "CI producer branch identity is invalid"
            )
        producer_head_sha = card.get("producer_head_sha")
        if (
            not isinstance(producer_head_sha, str)
            or _SHA_RE.fullmatch(producer_head_sha) is None
        ):
            raise SpineCiQualificationVerifyError(
                "CI producer head SHA is invalid"
            )
        head_sha = card.get("head_sha")
        if not isinstance(head_sha, str) or _SHA_RE.fullmatch(head_sha) is None:
            raise SpineCiQualificationVerifyError(
                "CI qualification head SHA is invalid"
            )
        for field in (
            "required_check_policy_digest",
            "checks_digest",
            "qualification_identity",
            "attestation_digest",
        ):
            value = card.get(field)
            if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
                raise SpineCiQualificationVerifyError(f"{field} is invalid")
        count = card.get("required_check_count")
        names = card.get("check_names")
        checks = card.get("checks")
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
        if count != len(REQUIRED_CHECKS) or names != list(REQUIRED_CHECKS):
            raise SpineCiQualificationVerifyError(
                "CI required-check catalog does not match policy"
            )
        if not isinstance(checks, list) or len(checks) != count:
            raise SpineCiQualificationVerifyError(
                "CI check evidence catalog is invalid"
            )
        normalized_checks: list[dict[str, Any]] = []
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                raise SpineCiQualificationVerifyError(
                    "CI check evidence must be an object"
                )
            name = check.get("name")
            if name != names[index]:
                raise SpineCiQualificationVerifyError(
                    "CI check evidence order or identity changed"
                )
            expected_path = REQUIRED_CHECK_WORKFLOWS.get(name)
            if (
                expected_path is None
                or check.get("workflow_path") != expected_path
                or check.get("event") != REQUIRED_CHECK_EVENT
            ):
                raise SpineCiQualificationVerifyError(
                    f"CI workflow identity mismatch: {name}"
                )
            workflow_digest = check.get("workflow_digest")
            if (
                not isinstance(workflow_digest, str)
                or _DIGEST_RE.fullmatch(workflow_digest) is None
            ):
                raise SpineCiQualificationVerifyError(
                    f"CI workflow definition digest is invalid: {name}"
                )
            if check.get("head_sha") != head_sha:
                raise SpineCiQualificationVerifyError(
                    f"CI check is not exact-head: {name}"
                )
            if check.get("conclusion") != "success":
                raise SpineCiQualificationVerifyError(
                    f"CI check is not successful: {name}"
                )
            run_id = check.get("run_id")
            run_attempt = check.get("run_attempt")
            if (
                isinstance(run_id, bool)
                or not isinstance(run_id, int)
                or run_id < 1
            ):
                raise SpineCiQualificationVerifyError(
                    f"CI run id is invalid: {name}"
                )
            if (
                isinstance(run_attempt, bool)
                or not isinstance(run_attempt, int)
                or run_attempt < 1
            ):
                raise SpineCiQualificationVerifyError(
                    f"CI run attempt is invalid: {name}"
                )
            normalized_checks.append(
                {
                    "name": name,
                    "head_sha": head_sha,
                    "workflow_path": expected_path,
                    "event": REQUIRED_CHECK_EVENT,
                    "workflow_digest": workflow_digest,
                    "run_id": run_id,
                    "run_attempt": run_attempt,
                    "conclusion": "success",
                }
            )
        if _digest(normalized_checks) != card["checks_digest"]:
            raise SpineCiQualificationVerifyError(
                "CI checks digest does not match check evidence"
            )
        if (
            card.get("required_check_policy_digest")
            != REQUIRED_CHECK_POLICY_DIGEST
        ):
            raise SpineCiQualificationVerifyError(
                "CI required-check policy digest mismatch"
            )
        expected_identity = _digest(
            {
                "repository": repository,
                "head_sha": head_sha,
                "required_check_policy_digest": REQUIRED_CHECK_POLICY_DIGEST,
                "checks_digest": card["checks_digest"],
            }
        )
        if card["qualification_identity"] != expected_identity:
            raise SpineCiQualificationVerifyError(
                "CI qualification identity mismatch"
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
            "authority_domain": card["authority_domain"],
            "repository": repository,
            "producer_workflow_name": card["producer_workflow_name"],
            "producer_workflow_path": card["producer_workflow_path"],
            "producer_event": card["producer_event"],
            "producer_workflow_id": card["producer_workflow_id"],
            "producer_run_id": card["producer_run_id"],
            "producer_run_attempt": card["producer_run_attempt"],
            "producer_status": card["producer_status"],
            "producer_head_repository": card[
                "producer_head_repository"
            ],
            "producer_head_branch": producer_head_branch,
            "producer_head_sha": producer_head_sha,
            "head_sha": head_sha,
            "required_check_policy_digest": card[
                "required_check_policy_digest"
            ],
            "required_check_count": count,
            "checks": normalized_checks,
            "checks_digest": card["checks_digest"],
            "qualification_identity": card["qualification_identity"],
            "check_names": list(names),
            "attestation_digest": card["attestation_digest"],
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
            "repository": repository,
            "head_sha": head_sha,
            "required_check_policy_digest": card["required_check_policy_digest"],
            "qualification_digest": digest,
            "qualification_identity": expected_identity,
            "verified": True,
            "ci_green": True,
            "merge_authority": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
