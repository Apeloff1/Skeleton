#!/usr/bin/env python3
"""Independent exact-head verifier for the AI system-completion plane.

The runtime acceptance test proves behavior.  This verifier proves that the
machine contract, runtime requirement inventory, acceptance bindings, and CI
wiring all describe the same non-compensable closure surface on the exact head.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "machine" / "ai_system_completion_contract.json"
RUNTIME_PATH = ROOT / "skeleton" / "ai" / "runtime" / "system_completion.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ai-system-completion.yml"
RUNTIME_TEST_PATH = (
    ROOT / "skeleton" / "testing" / "test_ai_system_completion_plane.py"
)
VERIFIER_TEST_PATH = ROOT / "tests" / "test_ai_system_completion_verifier.py"
QUALIFICATION_PATH = (
    ROOT / "skeleton" / "ai" / "evaluation" / "system_qualification.py"
)
QUALIFICATION_CLI_PATH = (
    ROOT / "scripts" / "run_ai_system_completion_qualification.py"
)
QUALIFICATION_TEST_PATH = ROOT / "tests" / "test_ai_system_qualification.py"
QUALIFICATION_RECEIPT_VERIFIER_PATH = (
    ROOT / "scripts" / "verify_ai_system_qualification_receipt.py"
)
QUALIFICATION_RECEIPT_VERIFIER_TEST_PATH = (
    ROOT / "tests" / "test_ai_system_qualification_receipt_verifier.py"
)
SECURITY_BINDING_PATHS = tuple(
    ROOT / path
    for path in (
        "skeleton/ai/runtime/sandbox/fs.py",
        "skeleton/ai/runtime/sandbox/process.py",
        "skeleton/ai/runtime/sandbox/injection.py",
        "skeleton/ai/runtime/sandbox/sanitizers.py",
        "skeleton/ai/shell/model_port.py",
        "skeleton/ai/shell/provider_router.py",
        "skeleton/memory/policy.py",
        "skeleton/memory/writeback.py",
        "skeleton/security/outbound_url.py",
        "skeleton/security/outbound_http.py",
        "skeleton/testing/test_sandbox_isolation.py",
        "skeleton/testing/test_sandbox_sanitize_inject.py",
        "skeleton/testing/test_shell_ai_observation_metrics_audit.py",
        "skeleton/testing/test_memory_writeback.py",
        "skeleton/testing/test_outbound_url_resolution_security.py",
        "skeleton/testing/test_security_outbound_http.py",
        ".github/workflows/p0-provider-fallback-privacy.yml",
        ".github/workflows/p0-memory-poisoning-evidence.yml",
        ".github/workflows/p0-network-boundary-evidence.yml",
        "skeleton/intelligence/admission.py",
        "skeleton/intelligence/admission_runtime.py",
        "skeleton/intelligence/quota.py",
        "skeleton/intelligence/shared_pressure.py",
        "skeleton/persistence/memory_repository.py",
        "skeleton/testing/test_admission_runtime.py",
        "skeleton/testing/test_execution_repository.py",
        "skeleton/persistence/execution_repository.py",
    )
)
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("system completion contract must be an object")
    return payload


def _runtime_requirements() -> list[str]:
    # Import only the completion module's public inventory.  The repository is
    # already on PYTHONPATH in CI and this prevents a second hand-maintained list.
    from skeleton.ai.runtime.system_completion import (  # noqa: PLC0415
        REQUIRED_COMPLETION_REQUIREMENTS,
    )

    return [item.value for item in REQUIRED_COMPLETION_REQUIREMENTS]


def _contains_all(path: Path, needles: Iterable[str]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [needle for needle in needles if needle not in text]


def verify(head_sha: str) -> dict[str, object]:
    errors: list[str] = []
    head_sha = head_sha.strip()
    if _GIT_SHA.fullmatch(head_sha) is None:
        errors.append("head_sha must be a lowercase 40-character git sha")

    required_files = (
        CONTRACT_PATH,
        RUNTIME_PATH,
        WORKFLOW_PATH,
        RUNTIME_TEST_PATH,
        VERIFIER_TEST_PATH,
        QUALIFICATION_PATH,
        QUALIFICATION_CLI_PATH,
        QUALIFICATION_TEST_PATH,
        QUALIFICATION_RECEIPT_VERIFIER_PATH,
        QUALIFICATION_RECEIPT_VERIFIER_TEST_PATH,
        *SECURITY_BINDING_PATHS,
    )
    missing_files = [str(path.relative_to(ROOT)) for path in required_files if not path.is_file()]
    if missing_files:
        errors.append("missing required files: " + ", ".join(sorted(missing_files)))

    contract: dict[str, object] = {}
    if CONTRACT_PATH.is_file():
        try:
            contract = _load_contract()
        except Exception as exc:  # pragma: no cover - surfaced in receipt
            errors.append(f"contract parse failed: {exc}")

    requirements = contract.get("required_requirements", [])
    if not isinstance(requirements, list) or not all(
        isinstance(item, str) and item for item in requirements
    ):
        errors.append("contract required_requirements must be non-empty strings")
        requirements = []
    if len(requirements) != len(set(requirements)):
        errors.append("contract contains duplicate requirements")

    runtime_requirements: list[str] = []
    if RUNTIME_PATH.is_file():
        try:
            runtime_requirements = _runtime_requirements()
        except Exception as exc:  # pragma: no cover - surfaced in receipt
            errors.append(f"runtime requirement import failed: {exc}")
    if requirements != runtime_requirements:
        errors.append("machine contract and runtime requirement inventory diverge")

    authority = contract.get("authority")
    required_authority = {
        "producer_must_differ_from_verifier": True,
        "exact_subject_binding": True,
        "exact_source_revision_binding": True,
        "duplicate_proofs_forbidden": True,
        "missing_proofs_fail_closed": True,
        "failed_proofs_non_compensable": True,
        "proof_source_revision_binding": True,
        "cross_execution_evidence_mixing_forbidden": True,
        "verification_candidate_context_binding": True,
        "learning_evaluation_lineage_required": True,
        "evidence_source_execution_binding": True,
        "learning_result_binding_required": True,
        "qualification_receipt_rehash_required": True,
        "strict_json_receipt_verification": True,
        "staged_finalization_crash_recovery_required": True,
        "negative_learning_gate_qualification_required": True,
        "sandbox_boundary_qualification_required": True,
        "injection_sanitization_qualification_required": True,
        "provider_privacy_fallback_qualification_required": True,
        "memory_poisoning_resistance_required": True,
        "outbound_network_boundary_qualification_required": True,
        "qualification_semantic_reverification_required": True,
        "resource_admission_qualification_required": True,
        "shared_pressure_qualification_required": True,
        "idempotent_retry_qualification_required": True,
        "tenant_isolation_qualification_required": True,
        "unknown_usage_terminal_fence_required": True,
        "verification_receipt_identity_required": True,
        "terminal_outbox_delivery_required": True,
        "persisted_terminal_evidence_integrity_required": True,
    }
    if not isinstance(authority, dict):
        errors.append("contract authority must be an object")
    else:
        for key, expected in required_authority.items():
            if authority.get(key) is not expected:
                errors.append(f"authority control disabled or missing: {key}")

    inherited_security = contract.get(
        "inherited_security_bindings",
        [],
    )
    if not isinstance(inherited_security, list) or not all(
        isinstance(item, str) and item for item in inherited_security
    ):
        errors.append(
            "inherited_security_bindings must be a string list"
        )
        inherited_security = []
    expected_security = [
        str(path.relative_to(ROOT)) for path in SECURITY_BINDING_PATHS
    ]
    if inherited_security != expected_security:
        errors.append(
            "inherited security binding inventory diverges"
        )

    bindings = contract.get("acceptance_bindings", [])
    if not isinstance(bindings, list) or not all(isinstance(item, str) for item in bindings):
        errors.append("acceptance_bindings must be a string list")
        bindings = []
    for binding in bindings:
        if not (ROOT / binding).is_file():
            errors.append(f"acceptance binding missing: {binding}")

    if RUNTIME_TEST_PATH.is_file():
        runtime_test_required = (
            "SystemCompletionPlane",
            "REQUIRED_COMPLETION_REQUIREMENTS",
            "test_system_completion_plane_composes_real_runtime_planes",
            "test_missing_requirement_cannot_be_compensated_by_other_green_proofs",
        )
        absent = _contains_all(RUNTIME_TEST_PATH, runtime_test_required)
        if absent:
            errors.append(
                "runtime acceptance wiring incomplete: " + ", ".join(absent)
            )

    if QUALIFICATION_PATH.is_file():
        qualification_required = (
            "qualify_system_completion",
            "SystemQualificationReceipt",
            "OfflineSocketGuard",
            "prove_reproducibility",
            "prove_learning_rollback",
            "_hostile_environment_cycle",
            "prove_sandbox_filesystem",
            "prove_sandbox_process",
            "prove_injection_sanitization",
            "prove_provider_fallback_privacy",
            "prove_memory_poisoning_resistance",
            "prove_outbound_network_boundary",
            "_resource_isolation_cycle",
            "prove_resource_admission",
            "prove_shared_pressure",
            "prove_idempotent_retry",
            "prove_tenant_isolation",
            "_persistence_reliability_cycle",
            "prove_unknown_usage_fence",
            "prove_verification_receipt_identity",
            "prove_terminal_outbox_delivery",
            "prove_persisted_evidence_integrity",
        )
        absent = _contains_all(QUALIFICATION_PATH, qualification_required)
        if absent:
            errors.append(
                "qualification runner wiring incomplete: " + ", ".join(absent)
            )

    if QUALIFICATION_RECEIPT_VERIFIER_PATH.is_file():
        receipt_verifier_required = (
            "object_pairs_hook=_reject_duplicate_pairs",
            "proof digest mismatch",
            "system-completion report digest mismatch",
            "qualification receipt digest mismatch",
            "canonical requirement order",
            "proof semantic pass mismatch",
            "_semantic_pass",
        )
        absent = _contains_all(
            QUALIFICATION_RECEIPT_VERIFIER_PATH,
            receipt_verifier_required,
        )
        if absent:
            errors.append(
                "qualification receipt verifier wiring incomplete: "
                + ", ".join(absent)
            )

    if QUALIFICATION_CLI_PATH.is_file():
        qualification_cli_required = (
            "qualify_system_completion",
            "--head-sha",
            "--evidence-out",
            "receipt.get(\"valid\")",
        )
        absent = _contains_all(
            QUALIFICATION_CLI_PATH,
            qualification_cli_required,
        )
        if absent:
            errors.append(
                "qualification CLI wiring incomplete: " + ", ".join(absent)
            )

    if WORKFLOW_PATH.is_file():
        workflow_required = (
            "test_ai_system_completion_plane.py",
            "test_ai_system_completion_verifier.py",
            "verify_ai_system_completion.py",
            "run_ai_system_completion_qualification.py",
            "verify_ai_system_qualification_receipt.py",
            "test_sandbox_isolation.py",
            "test_sandbox_sanitize_inject.py",
            "test_memory_writeback.py",
            "test_outbound_url_resolution_security.py",
            "test_admission_runtime.py",
            "test_execution_repository.py",
            ".ai-system-runtime-qualification.json",
            ".ai-system-runtime-qualification-verification.json",
            "github.event.pull_request.head.sha || github.sha",
        )
        absent = _contains_all(WORKFLOW_PATH, workflow_required)
        if absent:
            errors.append("workflow wiring incomplete: " + ", ".join(absent))

    file_digests = {
        str(path.relative_to(ROOT)): _sha256(path)
        for path in required_files
        if path.is_file()
    }
    contract_digest = _sha256(CONTRACT_PATH) if CONTRACT_PATH.is_file() else None

    receipt: dict[str, object] = {
        "schema_version": "skeleton.ai.system_completion_verifier_receipt.v1",
        "verifier": "independent-ai-system-completion-v1",
        "head_sha": head_sha,
        "requirement_count": len(requirements),
        "requirements": list(requirements),
        "runtime_requirements": runtime_requirements,
        "binding_count": len(bindings),
        "contract_digest": contract_digest,
        "file_digests": file_digests,
        "errors": errors,
        "valid": not errors,
    }
    receipt["receipt_digest"] = hashlib.sha256(_canonical(receipt)).hexdigest()
    return receipt


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head-sha", default=None)
    parser.add_argument("--evidence-out", default=None)
    parser.add_argument("--print-evidence", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    head_sha = args.head_sha or _git_head()
    receipt = verify(head_sha)
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.evidence_out:
        output = Path(args.evidence_out)
        if not output.is_absolute():
            output = ROOT / output
        output.write_text(encoded, encoding="utf-8")
    if args.print_evidence:
        print(encoded, end="")
    if not receipt["valid"]:
        for error in receipt["errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
