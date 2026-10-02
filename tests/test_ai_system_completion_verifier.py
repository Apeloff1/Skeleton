from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_ai_system_completion import verify


HEAD = "b" * 40


def test_system_completion_verifier_accepts_canonical_contract() -> None:
    receipt = verify(HEAD)
    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == HEAD
    assert receipt["verifier"] == "independent-ai-system-completion-v1"
    assert receipt["requirement_count"] == 32
    assert receipt["binding_count"] >= 9
    assert len(receipt["receipt_digest"]) == 64
    assert receipt["requirements"] == receipt["runtime_requirements"]


def test_contract_declares_non_compensable_authority() -> None:
    contract = json.loads(
        Path("machine/ai_system_completion_contract.json").read_text(
            encoding="utf-8"
        )
    )
    authority = contract["authority"]
    assert authority == {
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


@pytest.mark.parametrize(
    "value",
    [
        "",
        "abc",
        "A" * 40,
        "g" * 40,
        "0" * 39,
        "0" * 41,
    ],
)
def test_verifier_rejects_non_exact_head_identity(value: str) -> None:
    receipt = verify(value)
    assert receipt["valid"] is False
    assert any("head_sha" in error for error in receipt["errors"])


def test_required_runtime_and_acceptance_files_are_digest_bound() -> None:
    receipt = verify(HEAD)
    digests = receipt["file_digests"]
    assert set(digests) >= {
        "machine/ai_system_completion_contract.json",
        "skeleton/ai/runtime/system_completion.py",
        "skeleton/testing/test_ai_system_completion_plane.py",
        "tests/test_ai_system_completion_verifier.py",
        ".github/workflows/ai-system-completion.yml",
        "skeleton/ai/evaluation/system_qualification.py",
        "scripts/run_ai_system_completion_qualification.py",
        "tests/test_ai_system_qualification.py",
        "scripts/verify_ai_system_qualification_receipt.py",
        "tests/test_ai_system_qualification_receipt_verifier.py",
        "skeleton/ai/runtime/sandbox/fs.py",
        "skeleton/ai/runtime/sandbox/process.py",
        "skeleton/ai/runtime/sandbox/injection.py",
        "skeleton/ai/runtime/sandbox/sanitizers.py",
        "skeleton/ai/shell/provider_router.py",
        "skeleton/memory/writeback.py",
        "skeleton/security/outbound_url.py",
        "skeleton/security/outbound_http.py",
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
    }
    assert all(len(value) == 64 for value in digests.values())
