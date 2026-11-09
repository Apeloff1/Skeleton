"""Build one externally attestable exact-head CI receipt from workflow runs."""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Mapping

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


class SpineCiReceiptError(RuntimeError):
    """Required-check workflow evidence could not form a trusted receipt."""


class SpineCiReceiptIncompleteError(SpineCiReceiptError):
    """Required-check catalog is not complete and green yet."""


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$"
)


def _positive(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SpineCiReceiptError(f"{field} is invalid")
    return value


def _digest_text(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise SpineCiReceiptError(f"{field} is invalid")
    return value


class SpineCiReceiptBuilder:
    """Normalize the latest exact-head required workflow run for every policy check."""

    def build(
        self,
        *,
        workflow_runs: Iterable[Mapping[str, Any]],
        workflow_definitions: Mapping[str, Mapping[str, str]],
        expected_repository: str,
        producer_run: Mapping[str, Any],
        expected_producer_run_id: int,
        expected_producer_run_attempt: int,
        expected_producer_branch: str,
        expected_head_sha: str,
        attest: Callable[[dict[str, Any]], str],
    ) -> dict[str, Any]:
        if (
            not isinstance(expected_repository, str)
            or _REPOSITORY_RE.fullmatch(expected_repository) is None
        ):
            raise SpineCiReceiptError("expected repository is invalid")
        if not isinstance(workflow_definitions, Mapping):
            raise SpineCiReceiptError(
                "CI workflow definitions must be an object"
            )
        if not isinstance(producer_run, Mapping):
            raise SpineCiReceiptError("CI producer workflow run must be an object")
        producer_run_id = _positive(
            expected_producer_run_id,
            "CI producer run id",
        )
        producer_run_attempt = _positive(
            expected_producer_run_attempt,
            "CI producer run attempt",
        )
        if (
            not isinstance(expected_producer_branch, str)
            or not expected_producer_branch.strip()
        ):
            raise SpineCiReceiptError("CI producer branch is invalid")
        if not isinstance(expected_head_sha, str) or _SHA_RE.fullmatch(expected_head_sha) is None:
            raise SpineCiReceiptError("expected head SHA is invalid")

        observed_producer_run_id = _positive(
            producer_run.get("id"),
            "observed CI producer run id",
        )
        observed_producer_attempt = _positive(
            producer_run.get("run_attempt"),
            "observed CI producer run attempt",
        )
        producer_workflow_id = _positive(
            producer_run.get("workflow_id"),
            "CI producer workflow id",
        )
        if observed_producer_run_id != producer_run_id:
            raise SpineCiReceiptError("CI producer run identity changed")
        if observed_producer_attempt != producer_run_attempt:
            raise SpineCiReceiptError("CI producer run attempt changed")
        if producer_run.get("name") != CI_PRODUCER_WORKFLOW_NAME:
            raise SpineCiReceiptError("CI producer workflow name changed")
        if producer_run.get("path") != CI_PRODUCER_WORKFLOW_PATH:
            raise SpineCiReceiptError("CI producer workflow path changed")
        if producer_run.get("event") != CI_PRODUCER_EVENT:
            raise SpineCiReceiptError("CI producer event changed")
        if producer_run.get("status") != CI_PRODUCER_STATUS:
            raise SpineCiReceiptError("CI producer is not running")
        if producer_run.get("conclusion") is not None:
            raise SpineCiReceiptError(
                "CI producer concluded before evidence emission"
            )
        producer_head_sha = producer_run.get("head_sha")
        if (
            not isinstance(producer_head_sha, str)
            or _SHA_RE.fullmatch(producer_head_sha) is None
        ):
            raise SpineCiReceiptError("CI producer head SHA is invalid")
        if producer_run.get("head_branch") != expected_producer_branch:
            raise SpineCiReceiptError("CI producer branch identity changed")
        producer_head_repository = producer_run.get("head_repository")
        producer_repository = (
            producer_head_repository.get("full_name")
            if isinstance(producer_head_repository, Mapping)
            else None
        )
        if producer_repository != expected_repository:
            raise SpineCiReceiptError("CI producer repository changed")
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
            definition = workflow_definitions.get(name)
            if not isinstance(definition, Mapping):
                raise SpineCiReceiptError(
                    f"CI workflow definition evidence missing: {name}"
                )
            head_definition_digest = _digest_text(
                definition.get("head_digest"),
                f"{name} head workflow definition digest",
            )
            trusted_definition_digest = _digest_text(
                definition.get("trusted_digest"),
                f"{name} trusted workflow definition digest",
            )
            if head_definition_digest != trusted_definition_digest:
                raise SpineCiReceiptError(
                    f"CI workflow definition differs from trusted default branch: {name}"
                )
            run_id = _positive(raw.get("id"), f"{name} run id")
            run_attempt = _positive(raw.get("run_attempt"), f"{name} run attempt")
            candidate = {
                "name": name,
                "head_sha": expected_head_sha,
                "workflow_path": REQUIRED_CHECK_WORKFLOWS[name],
                "event": REQUIRED_CHECK_EVENT,
                "workflow_digest": head_definition_digest,
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
                "workflow_digest": latest[name]["workflow_digest"],
                "run_id": latest[name]["run_id"],
                "run_attempt": latest[name]["run_attempt"],
                "conclusion": "success",
            }
            for name in REQUIRED_CHECKS
        ]
        receipt: dict[str, Any] = {
            "kind": "spine_ci_exact_head_receipt",
            "authority_domain": "ci-exact-head",
            "repository": expected_repository,
            "producer_workflow_name": CI_PRODUCER_WORKFLOW_NAME,
            "producer_workflow_path": CI_PRODUCER_WORKFLOW_PATH,
            "producer_event": CI_PRODUCER_EVENT,
            "producer_workflow_id": producer_workflow_id,
            "producer_run_id": producer_run_id,
            "producer_run_attempt": producer_run_attempt,
            "producer_status": CI_PRODUCER_STATUS,
            "producer_head_repository": producer_repository,
            "producer_head_branch": expected_producer_branch,
            "producer_head_sha": producer_head_sha,
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
