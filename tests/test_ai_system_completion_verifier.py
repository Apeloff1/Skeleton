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
    assert receipt["requirement_count"] == 16
    assert receipt["binding_count"] >= 4
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
    }
    assert all(len(value) == 64 for value in digests.values())
