#!/usr/bin/env python3
"""Independently verify an emitted AI system-qualification receipt.

This verifier intentionally does not trust the receipt's stored `valid` flags
or digests. It reparses JSON with duplicate-key rejection, recomputes every
proof digest, recomputes the system-completion report, and finally recomputes
the qualification receipt digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "machine" / "ai_system_completion_contract.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
PROOF_KEYS = {
    "requirement",
    "subject_id",
    "source_revision",
    "passed",
    "producer_id",
    "verifier_id",
    "evidence_refs",
    "details",
    "digest",
}
REPORT_KEYS = {
    "schema_version",
    "subject_id",
    "source_revision",
    "required",
    "proofs",
    "missing",
    "failed",
    "valid",
    "digest",
}
RECEIPT_KEYS = {
    "schema_version",
    "source_revision",
    "subject_id",
    "report",
    "primary_result_digest",
    "replay_result_digest",
    "primary_output_digest",
    "replay_output_digest",
    "network_attempt_count",
    "observed_tool_ids",
    "replay_observed_tool_ids",
    "validity_checks",
    "invalid_reasons",
    "valid",
    "digest",
}


class ReceiptVerificationError(ValueError):
    """Raised when qualification evidence is malformed or forged."""


def _reject_duplicate_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptVerificationError(
                f"duplicate JSON object key: {key}"
            )
        result[key] = value
    return result


def _load_strict_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ReceiptVerificationError(
            f"cannot load strict JSON: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise ReceiptVerificationError(
            f"expected top-level JSON object: {path}"
        )
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReceiptVerificationError(
            "receipt contains non-canonical JSON values"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ReceiptVerificationError(f"{name} must be non-empty text")
    if value.strip() != value:
        raise ReceiptVerificationError(f"{name} is not normalized")
    return value


def _sha256(name: str, value: object) -> str:
    text = _text(name, value)
    if _SHA256.fullmatch(text) is None:
        raise ReceiptVerificationError(
            f"{name} must be lowercase sha256"
        )
    return text


def _git_sha(name: str, value: object) -> str:
    text = _text(name, value)
    if _GIT_SHA.fullmatch(text) is None:
        raise ReceiptVerificationError(
            f"{name} must be lowercase 40-char git sha"
        )
    return text


def _exact_keys(
    name: str,
    value: dict[str, Any],
    expected: set[str],
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ReceiptVerificationError(
            f"{name} keys diverge; missing={missing} extra={extra}"
        )


def _string_list(
    name: str,
    value: object,
    *,
    require_unique: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise ReceiptVerificationError(f"{name} must be a list")
    result = [_text(name, item) for item in value]
    if require_unique and len(result) != len(set(result)):
        raise ReceiptVerificationError(
            f"{name} contains duplicate values"
        )
    return result


def _contract_requirements() -> tuple[list[str], str]:
    contract = _load_strict_json(CONTRACT_PATH)
    required = _string_list(
        "contract.required_requirements",
        contract.get("required_requirements"),
        require_unique=True,
    )
    if len(required) != 28:
        raise ReceiptVerificationError(
            "completion contract must retain exactly 28 requirements"
        )
    return required, _digest(contract)


def _boolean(details: dict[str, Any], key: str) -> bool:
    value = details.get(key)
    if not isinstance(value, bool):
        raise ReceiptVerificationError(
            f"proof detail {key} must be boolean"
        )
    return value


def _integer(
    details: dict[str, Any],
    key: str,
    *,
    minimum: int = 0,
) -> int:
    value = details.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
    ):
        raise ReceiptVerificationError(
            f"proof detail {key} must be integer >= {minimum}"
        )
    return value


def _detail_text(details: dict[str, Any], key: str) -> str:
    return _text(f"proof.details.{key}", details.get(key))


def _detail_sha(details: dict[str, Any], key: str) -> str:
    return _sha256(f"proof.details.{key}", details.get(key))


def _detail_text_list(
    details: dict[str, Any],
    key: str,
) -> list[str]:
    return _string_list(
        f"proof.details.{key}",
        details.get(key),
    )


def _semantic_pass(
    requirement: str,
    details: dict[str, Any],
    evidence_refs: list[str],
    *,
    expected_subject: str,
) -> bool:
    subject_bound = details.get("subject_bound")
    if "subject_bound" in details and subject_bound is not True:
        return False

    if requirement == "execution.local_model":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _detail_text(details, "state") == "completed"
            and _integer(
                details,
                "provider_receipt_count",
                minimum=1,
            ) >= 1
            and any(
                ref.startswith("provider:local:")
                for ref in evidence_refs
            )
        )

    if requirement == "execution.offline_isolation":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _integer(details, "network_attempt_count") == 0
            and _integer(
                details,
                "provider_receipt_count",
                minimum=1,
            ) >= 1
            and _boolean(
                details,
                "all_provider_receipts_local",
            )
        )

    if requirement == "execution.request_result_binding":
        request_execution = _detail_text(
            details,
            "request_execution_id",
        )
        result_execution = _detail_text(
            details,
            "result_execution_id",
        )
        return bool(
            request_execution == expected_subject
            and result_execution == expected_subject
            and _detail_text(
                details,
                "request_operation_id",
            )
            == _detail_text(
                details,
                "result_operation_id",
            )
            and _SHA256.fullmatch(
                _detail_text(
                    details,
                    "request_identity_digest",
                )
            )
            is not None
        )

    if requirement == "execution.budget_bounds":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _integer(
                details,
                "observed_model_turns",
                minimum=1,
            )
            <= _integer(
                details,
                "max_model_turns",
                minimum=1,
            )
            and _integer(details, "observed_tool_calls")
            <= _integer(
                details,
                "max_tool_calls",
                minimum=1,
            )
        )

    if requirement == "execution.stop_semantics":
        return bool(
            _detail_text(details, "deadline_status") == "failed"
            and _detail_text(
                details,
                "deadline_error_code",
            )
            == "execution_deadline_exceeded"
            and _boolean(details, "deadline_fenced")
            and _detail_text(
                details,
                "cancellation_status",
            )
            == "cancelled"
            and _detail_text(
                details,
                "cancellation_error_code",
            )
            == "cancellation_requested"
            and _boolean(details, "cancellation_fenced")
        )

    if requirement == "execution.tool_authority":
        allowed = _detail_text_list(
            details,
            "allowed_tool_ids",
        )
        observed = _detail_text_list(
            details,
            "observed_tool_ids",
        )
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and observed
            and _integer(
                details,
                "observed_call_count",
                minimum=1,
            )
            == len(observed)
            and _integer(
                details,
                "receipt_count",
                minimum=1,
            )
            == len(observed)
            and _boolean(details, "all_calls_authorized")
            and all(item in allowed for item in observed)
        )

    if requirement == "execution.durable_recovery":
        live_digest = _detail_sha(details, "live_digest")
        recovered_digest = _detail_sha(
            details,
            "recovered_digest",
        )
        return bool(
            _detail_text(
                details,
                "live_execution_id",
            )
            == expected_subject
            and _detail_text(
                details,
                "recovered_execution_id",
            )
            == expected_subject
            and live_digest == recovered_digest
            and _boolean(details, "exact_match")
        )

    if requirement == "execution.staged_finalization_recovery":
        return bool(
            _detail_text(
                details,
                "staged_execution_id",
            )
            == expected_subject
            and _detail_text(
                details,
                "recovered_execution_id",
            )
            == expected_subject
            and _boolean(details, "exact_match")
            and _boolean(details, "intent_cleared")
        )

    if requirement == "execution.replay_lineage":
        return bool(
            _integer(details, "turn_count", minimum=1) >= 1
            and all(
                _boolean(details, key)
                for key in (
                    "contiguous",
                    "subject_bound",
                    "operation_bound",
                    "unique_turn_ids",
                    "parent_linked",
                    "checkpoints_bound",
                )
            )
        )

    if requirement == "execution.reproducibility":
        return bool(
            _detail_text(
                details,
                "primary_execution_id",
            )
            == expected_subject
            and _detail_text(
                details,
                "replay_execution_id",
            )
            == expected_subject
            and _boolean(details, "result_equal")
            and _boolean(details, "output_equal")
        )

    if requirement == "execution.governed_effects":
        receipts = _integer(details, "tool_receipt_count")
        mutating = _integer(details, "mutating_tool_count")
        verified = _integer(
            details,
            "verified_postcondition_count",
        )
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and mutating <= receipts
            and verified == mutating
        )

    if requirement == "verification.independent":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _detail_text(details, "outcome") == "passed"
            and _boolean(details, "policy_satisfied")
            and _integer(
                details,
                "evidence_count",
                minimum=1,
            ) >= 1
        )

    if requirement == "verification.claim_binding":
        candidate = _detail_sha(details, "candidate_digest")
        receipt_candidate = _detail_sha(
            details,
            "receipt_candidate_digest",
        )
        context = _detail_sha(details, "context_digest")
        receipt_context = _detail_sha(
            details,
            "receipt_context_digest",
        )
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and candidate == receipt_candidate
            and context == receipt_context
        )

    if requirement == "context.integrity":
        problems = details.get("problems")
        if not isinstance(problems, list):
            raise ReceiptVerificationError(
                "proof detail problems must be a list"
            )
        return bool(
            _detail_text(
                details,
                "context_subject_id",
            )
            == expected_subject
            and _integer(details, "height", minimum=1) >= 1
            and _integer(details, "problem_count") == 0
            and problems == []
        )

    if requirement == "memory.lifecycle":
        return bool(
            _detail_text(
                details,
                "memory_subject_id",
            )
            == expected_subject
            and _boolean(
                details,
                "recalled_before_delete",
            )
            and _boolean(
                details,
                "delete_acknowledged",
            )
            and _boolean(
                details,
                "absent_after_delete",
            )
        )

    if requirement == "finalization.lineage":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _integer(
                details,
                "memory_ref_count",
                minimum=1,
            ) >= 1
            and _integer(
                details,
                "artifact_ref_count",
                minimum=1,
            ) >= 1
            and _boolean(
                details,
                "stream_terminal_bound",
            )
        )

    if requirement == "security.sandbox_filesystem":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _boolean(details, "safe_roundtrip")
            and _boolean(details, "traversal_rejected")
            and _boolean(details, "outside_untouched")
        )

    if requirement == "security.sandbox_process":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and all(
                _boolean(details, key)
                for key in (
                    "clean_environment",
                    "shell_string_rejected",
                    "bounded_execution",
                    "network_fail_closed",
                )
            )
        )

    if requirement == "security.injection_sanitization":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and all(
                _boolean(details, key)
                for key in (
                    "prompt_attack_blocked",
                    "shell_attack_blocked",
                    "secret_redacted",
                    "duplicate_json_rejected",
                )
            )
        )

    if requirement == "privacy.provider_fallback":
        boundaries = _detail_text_list(
            details,
            "routed_boundaries",
        )
        models = _detail_text_list(
            details,
            "routed_model_ids",
        )
        rank = {
            "local": 0,
            "private_remote": 1,
            "external": 2,
        }
        required = _detail_text(
            details,
            "required_boundary",
        )
        maximum = rank.get(required)
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and maximum is not None
            and boundaries
            and len(boundaries) == len(models)
            and all(
                item in rank and rank[item] <= maximum
                for item in boundaries
            )
            and _boolean(
                details,
                "all_within_boundary",
            )
        )

    if requirement == "memory.poisoning_resistance":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _detail_text(
                details,
                "committed_subject_id",
            )
            == expected_subject
            and _boolean(
                details,
                "memory_subject_bound",
            )
            and _boolean(
                details,
                "valid_write_committed",
            )
            and _boolean(
                details,
                "missing_provenance_denied",
            )
            and _boolean(
                details,
                "conflicting_replay_rejected",
            )
        )

    if requirement == "security.outbound_network_boundary":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and all(
                _boolean(details, key)
                for key in (
                    "private_target_rejected",
                    "mixed_dns_rejected",
                    "peer_rebinding_rejected",
                    "canonical_public_resolution",
                )
            )
        )

    if requirement == "resource.admission_quota":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _boolean(
                details,
                "admitted_within_budget",
            )
            and _boolean(
                details,
                "over_quota_rejected",
            )
            and _boolean(
                details,
                "denial_capacity_unchanged",
            )
            and _boolean(
                details,
                "usage_reconciled",
            )
        )

    if requirement == "resource.shared_pressure":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _boolean(
                details,
                "first_worker_admitted",
            )
            and _boolean(
                details,
                "second_worker_blocked",
            )
            and _boolean(
                details,
                "capacity_released",
            )
            and _boolean(
                details,
                "second_worker_admitted_after_release",
            )
        )

    if requirement == "execution.idempotent_retry":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _boolean(
                details,
                "identical_retry_stable",
            )
            and _boolean(
                details,
                "conflicting_retry_rejected",
            )
            and _boolean(
                details,
                "no_double_reservation",
            )
        )

    if requirement == "privacy.tenant_isolation":
        return bool(
            _detail_text(details, "execution_id") == expected_subject
            and _boolean(
                details,
                "owner_tenant_visible",
            )
            and _boolean(
                details,
                "other_tenant_hidden",
            )
            and _boolean(
                details,
                "cross_tenant_get_rejected",
            )
            and _boolean(
                details,
                "subject_scope_preserved",
            )
        )

    if requirement == "learning.promotion":
        expected_experiment = _detail_text(
            details,
            "expected_experiment_id",
        )
        return bool(
            _detail_text(details, "from_version")
            != _detail_text(details, "to_version")
            and _detail_text(details, "active_version")
            == _detail_text(details, "to_version")
            and _detail_sha(
                details,
                "evaluation_digest",
            )
            and _detail_text(details, "evaluator_id")
            != "learning-promotion-pipeline"
            and _detail_text(details, "experiment_id")
            == expected_experiment
            and _boolean(details, "result_bound")
            and _boolean(details, "evaluation_bound")
            and _boolean(
                details,
                "failed_evaluation_rejected",
            )
            and _boolean(
                details,
                "cross_experiment_rejected",
            )
            and details.get("rollback") is False
        )

    if requirement == "learning.rollback":
        expected_experiment = _detail_text(
            details,
            "expected_experiment_id",
        )
        return bool(
            _detail_text(details, "from_version")
            != _detail_text(details, "to_version")
            and _detail_text(details, "active_version")
            == _detail_text(details, "to_version")
            and bool(_detail_text(details, "reason"))
            and _detail_text(
                details,
                "promotion_experiment_id",
            )
            == expected_experiment
            and _detail_text(
                details,
                "rollback_experiment_id",
            )
            == expected_experiment
            and _boolean(details, "result_bound")
            and _detail_sha(
                details,
                "promotion_evaluation_digest",
            )
            == _detail_sha(
                details,
                "rollback_evaluation_digest",
            )
            and _boolean(
                details,
                "evaluation_lineage_preserved",
            )
            and _boolean(
                details,
                "rollback_without_promotion_rejected",
            )
            and details.get("rollback") is True
        )

    raise ReceiptVerificationError(
        f"no semantic verifier for requirement: {requirement}"
    )


def _proof_digest(
    proof: dict[str, Any],
    *,
    expected_subject: str,
    expected_revision: str,
) -> tuple[str, bool]:
    _exact_keys("proof", proof, PROOF_KEYS)

    requirement = _text("proof.requirement", proof["requirement"])
    subject_id = _text("proof.subject_id", proof["subject_id"])
    revision = _git_sha(
        "proof.source_revision",
        proof["source_revision"],
    )
    producer_id = _text("proof.producer_id", proof["producer_id"])
    verifier_id = _text("proof.verifier_id", proof["verifier_id"])
    passed = proof["passed"]
    if not isinstance(passed, bool):
        raise ReceiptVerificationError(
            "proof.passed must be boolean"
        )
    refs = _string_list(
        "proof.evidence_refs",
        proof["evidence_refs"],
        require_unique=True,
    )
    if passed and not refs:
        raise ReceiptVerificationError(
            "passing proof must carry evidence refs"
        )
    details = proof["details"]
    if not isinstance(details, dict):
        raise ReceiptVerificationError(
            "proof.details must be an object"
        )
    if subject_id != expected_subject:
        raise ReceiptVerificationError(
            "proof subject does not match receipt subject"
        )
    if revision != expected_revision:
        raise ReceiptVerificationError(
            "proof revision does not match receipt revision"
        )
    if producer_id == verifier_id:
        raise ReceiptVerificationError(
            "proof producer cannot self-verify"
        )

    semantic_passed = _semantic_pass(
        requirement,
        details,
        refs,
        expected_subject=expected_subject,
    )
    if passed is not semantic_passed:
        raise ReceiptVerificationError(
            f"proof semantic pass mismatch: {requirement}"
        )

    calculated = _digest(
        {
            "requirement": requirement,
            "subject_id": subject_id,
            "source_revision": revision,
            "passed": passed,
            "producer_id": producer_id,
            "verifier_id": verifier_id,
            "evidence_refs": refs,
            "details": details,
        }
    )
    stored = _sha256("proof.digest", proof["digest"])
    if calculated != stored:
        raise ReceiptVerificationError(
            f"proof digest mismatch: {requirement}"
        )
    return requirement, passed


def _report_digest(
    report: dict[str, Any],
    *,
    required: list[str],
    expected_subject: str,
    expected_revision: str,
) -> tuple[str, bool, list[str], list[str]]:
    _exact_keys("report", report, REPORT_KEYS)
    if report.get("schema_version") != "skeleton.ai.system_completion.v1":
        raise ReceiptVerificationError(
            "unexpected system-completion report schema"
        )
    subject_id = _text("report.subject_id", report["subject_id"])
    revision = _git_sha(
        "report.source_revision",
        report["source_revision"],
    )
    if subject_id != expected_subject:
        raise ReceiptVerificationError(
            "report subject does not match receipt subject"
        )
    if revision != expected_revision:
        raise ReceiptVerificationError(
            "report revision does not match receipt revision"
        )
    report_required = _string_list(
        "report.required",
        report["required"],
        require_unique=True,
    )
    if report_required != required:
        raise ReceiptVerificationError(
            "report requirement inventory diverges from contract"
        )

    raw_proofs = report["proofs"]
    if not isinstance(raw_proofs, list):
        raise ReceiptVerificationError("report.proofs must be a list")

    proofs: list[tuple[str, bool, str]] = []
    seen: set[str] = set()
    for raw in raw_proofs:
        if not isinstance(raw, dict):
            raise ReceiptVerificationError(
                "report proof must be an object"
            )
        requirement, passed = _proof_digest(
            raw,
            expected_subject=expected_subject,
            expected_revision=expected_revision,
        )
        if requirement in seen:
            raise ReceiptVerificationError(
                f"duplicate report proof: {requirement}"
            )
        seen.add(requirement)
        proofs.append((requirement, passed, raw["digest"]))

    canonical_order = sorted(
        (item[0] for item in proofs),
    )
    actual_order = [item[0] for item in proofs]
    if actual_order != canonical_order:
        raise ReceiptVerificationError(
            "report proofs are not in canonical requirement order"
        )

    unknown = sorted(set(actual_order) - set(required))
    if unknown:
        raise ReceiptVerificationError(
            f"report contains unknown requirements: {unknown}"
        )
    missing = [
        requirement
        for requirement in required
        if requirement not in seen
    ]
    failed = [
        requirement
        for requirement, passed, _digest_value in proofs
        if not passed
    ]
    valid = not missing and not failed

    if report["missing"] != missing:
        raise ReceiptVerificationError("report.missing is forged")
    if report["failed"] != failed:
        raise ReceiptVerificationError("report.failed is forged")
    if report["valid"] is not valid:
        raise ReceiptVerificationError("report.valid is forged")

    calculated = _digest(
        {
            "schema_version": "skeleton.ai.system_completion.v1",
            "subject_id": subject_id,
            "source_revision": revision,
            "required": required,
            "proof_digests": [item[2] for item in proofs],
            "missing": missing,
            "failed": failed,
            "valid": valid,
        }
    )
    stored = _sha256("report.digest", report["digest"])
    if calculated != stored:
        raise ReceiptVerificationError(
            "system-completion report digest mismatch"
        )
    return calculated, valid, missing, failed


def verify_receipt(
    receipt_path: str | Path,
    *,
    expected_head: str,
) -> dict[str, Any]:
    errors: list[str] = []
    calculated_receipt_digest: str | None = None
    contract_digest: str | None = None

    try:
        expected_revision = _git_sha(
            "expected_head",
            expected_head,
        )
        required, contract_digest = _contract_requirements()
        path = Path(receipt_path)
        if not path.is_absolute():
            path = ROOT / path
        receipt = _load_strict_json(path)
        _exact_keys("receipt", receipt, RECEIPT_KEYS)

        if (
            receipt.get("schema_version")
            != "skeleton.ai.system_qualification.v1"
        ):
            raise ReceiptVerificationError(
                "unexpected qualification receipt schema"
            )
        revision = _git_sha(
            "receipt.source_revision",
            receipt["source_revision"],
        )
        if revision != expected_revision:
            raise ReceiptVerificationError(
                "qualification receipt is not exact-head"
            )
        subject_id = _text(
            "receipt.subject_id",
            receipt["subject_id"],
        )

        report = receipt["report"]
        if not isinstance(report, dict):
            raise ReceiptVerificationError(
                "receipt.report must be an object"
            )
        report_digest, report_valid, missing, failed = _report_digest(
            report,
            required=required,
            expected_subject=subject_id,
            expected_revision=revision,
        )

        primary_result = _sha256(
            "receipt.primary_result_digest",
            receipt["primary_result_digest"],
        )
        replay_result = _sha256(
            "receipt.replay_result_digest",
            receipt["replay_result_digest"],
        )
        primary_output = _sha256(
            "receipt.primary_output_digest",
            receipt["primary_output_digest"],
        )
        replay_output = _sha256(
            "receipt.replay_output_digest",
            receipt["replay_output_digest"],
        )
        network_attempt_count = receipt["network_attempt_count"]
        if (
            isinstance(network_attempt_count, bool)
            or not isinstance(network_attempt_count, int)
            or network_attempt_count < 0
        ):
            raise ReceiptVerificationError(
                "network_attempt_count must be non-negative integer"
            )
        observed_tools = _string_list(
            "receipt.observed_tool_ids",
            receipt["observed_tool_ids"],
        )
        replay_tools = _string_list(
            "receipt.replay_observed_tool_ids",
            receipt["replay_observed_tool_ids"],
        )

        checks = {
            "report_valid": report_valid,
            "subject_bound": report["subject_id"] == subject_id,
            "source_revision_bound": (
                report["source_revision"] == revision
            ),
            "network_isolated": network_attempt_count == 0,
            "result_reproducible": primary_result == replay_result,
            "output_reproducible": primary_output == replay_output,
            "tool_trace_reproducible": observed_tools == replay_tools,
        }
        invalid_reasons = [
            name for name, passed in checks.items() if not passed
        ]
        valid = all(checks.values())

        if receipt["validity_checks"] != checks:
            raise ReceiptVerificationError(
                "receipt validity_checks are forged"
            )
        if receipt["invalid_reasons"] != invalid_reasons:
            raise ReceiptVerificationError(
                "receipt invalid_reasons are forged"
            )
        if receipt["valid"] is not valid:
            raise ReceiptVerificationError(
                "receipt.valid is forged"
            )

        calculated_receipt_digest = _digest(
            {
                "schema_version": "skeleton.ai.system_qualification.v1",
                "source_revision": revision,
                "subject_id": subject_id,
                "report_digest": report_digest,
                "primary_result_digest": primary_result,
                "replay_result_digest": replay_result,
                "primary_output_digest": primary_output,
                "replay_output_digest": replay_output,
                "network_attempt_count": network_attempt_count,
                "observed_tool_ids": observed_tools,
                "replay_observed_tool_ids": replay_tools,
                "validity_checks": checks,
                "valid": valid,
            }
        )
        stored_digest = _sha256(
            "receipt.digest",
            receipt["digest"],
        )
        if calculated_receipt_digest != stored_digest:
            raise ReceiptVerificationError(
                "qualification receipt digest mismatch"
            )
        if missing or failed or not valid:
            raise ReceiptVerificationError(
                "qualification receipt does not prove complete closure"
            )
    except ReceiptVerificationError as exc:
        errors.append(str(exc))

    verdict = {
        "schema_version":
            "skeleton.ai.system_qualification_verification.v1",
        "verifier":
            "independent-ai-system-qualification-receipt-v1",
        "expected_head": expected_head,
        "contract_digest": contract_digest,
        "receipt_digest": calculated_receipt_digest,
        "errors": errors,
        "valid": not errors,
    }
    verdict["verifier_digest"] = _digest(verdict)
    return verdict


def _args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt")
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--evidence-out", default=None)
    parser.add_argument("--print-evidence", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(list(sys.argv[1:] if argv is None else argv))
    verdict = verify_receipt(
        args.receipt,
        expected_head=args.head_sha,
    )
    encoded = json.dumps(verdict, indent=2, sort_keys=True) + "\n"
    if args.evidence_out:
        path = Path(args.evidence_out)
        if not path.is_absolute():
            path = ROOT / path
        path.write_text(encoded, encoding="utf-8")
    if args.print_evidence:
        print(encoded, end="")
    if verdict["valid"] is not True:
        for error in verdict["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
