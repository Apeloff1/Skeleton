"""Build one externally attestable exact-head CI receipt from workflow runs."""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Mapping

from skeleton.persistence.spine_ci_policy import (
    REQUIRED_CHECK_EVENT,
    REQUIRED_CHECK_POLICY_DIGEST,
    REQUIRED_CHECKS,
    REQUIRED_CHECK_WORKFLOWS,
)


class SpineCiReceiptError(RuntimeError):
    """Required-check workflow evidence could not form a trusted receipt."""


class SpineCiReceiptIncompleteError(SpineCiReceiptError):
    """Required-check catalog is not complete and green yet."""


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _positive(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SpineCiReceiptError(f"{field} is invalid")
    return value


class SpineCiReceiptBuilder:
    """Normalize the latest exact-head required workflow run for every policy check."""

    def build(
        self,
        *,
        workflow_runs: Iterable[Mapping[str, Any]],
        expected_head_sha: str,
        attest: Callable[[dict[str, Any]], str],
    ) -> dict[str, Any]:
        if not isinstance(expected_head_sha, str) or _SHA_RE.fullmatch(expected_head_sha) is None:
            raise SpineCiReceiptError("expected head SHA is invalid")
        if not callable(attest):
            raise SpineCiReceiptError("CI receipt attestor must be callable")

        latest: dict[str, dict[str, Any]] = {}
        for raw in workflow_runs:
            if not isinstance(raw, Mapping):
                raise SpineCiReceiptError("workflow run evidence must be an object")
            name = raw.get("name")
            if name not in REQUIRED_CHECKS:
                continue
            if raw.get("head_sha") != expected_head_sha:
                continue
            if raw.get("path") != REQUIRED_CHECK_WORKFLOWS[name]:
                raise SpineCiReceiptError(
                    f"CI workflow identity mismatch: {name}"
                )
            if raw.get("event") != REQUIRED_CHECK_EVENT:
                raise SpineCiReceiptError(
                    f"CI workflow event mismatch: {name}"
                )
            run_id = _positive(raw.get("id"), f"{name} run id")
            run_attempt = _positive(raw.get("run_attempt"), f"{name} run attempt")
            candidate = {
                "name": name,
                "head_sha": expected_head_sha,
                "workflow_path": REQUIRED_CHECK_WORKFLOWS[name],
                "event": REQUIRED_CHECK_EVENT,
                "run_id": run_id,
                "run_attempt": run_attempt,
                "status": raw.get("status"),
                "conclusion": raw.get("conclusion"),
            }
            existing = latest.get(name)
            if existing is None or (run_id, run_attempt) > (
                existing["run_id"],
                existing["run_attempt"],
            ):
                latest[name] = candidate

        missing = [name for name in REQUIRED_CHECKS if name not in latest]
        pending = [
            name
            for name in REQUIRED_CHECKS
            if name in latest and latest[name]["status"] != "completed"
        ]
        failing = [
            name
            for name in REQUIRED_CHECKS
            if name in latest
            and latest[name]["status"] == "completed"
            and latest[name]["conclusion"] != "success"
        ]
        if missing or pending or failing:
            raise SpineCiReceiptIncompleteError(
                "CI required-check catalog is not green: "
                f"missing={','.join(missing) or '-'}; "
                f"pending={','.join(pending) or '-'}; "
                f"failing={','.join(failing) or '-'}"
            )

        checks = [
            {
                "name": name,
                "head_sha": expected_head_sha,
                "workflow_path": latest[name]["workflow_path"],
                "event": latest[name]["event"],
                "run_id": latest[name]["run_id"],
                "run_attempt": latest[name]["run_attempt"],
                "conclusion": "success",
            }
            for name in REQUIRED_CHECKS
        ]
        receipt: dict[str, Any] = {
            "kind": "spine_ci_exact_head_receipt",
            "authority_domain": "ci-exact-head",
            "head_sha": expected_head_sha,
            "required_check_policy_digest": REQUIRED_CHECK_POLICY_DIGEST,
            "required_check_count": len(REQUIRED_CHECKS),
            "checks": checks,
            "catalog_complete": True,
            "pending_count": 0,
            "failing_count": 0,
            "missing_count": 0,
        }
        try:
            attestation = attest(dict(receipt))
        except Exception as exc:
            raise SpineCiReceiptError("CI receipt attestation failed closed") from exc
        if not isinstance(attestation, str) or _DIGEST_RE.fullmatch(attestation) is None:
            raise SpineCiReceiptError("CI attestation digest is invalid")
        receipt["attestation_digest"] = attestation
        return receipt


__all__ = [
    "SpineCiReceiptBuilder",
    "SpineCiReceiptError",
    "SpineCiReceiptIncompleteError",
]
