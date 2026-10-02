from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from scripts.verify_ai_system_qualification_receipt import verify_receipt
from skeleton.ai.evaluation.system_qualification import (
    qualify_system_completion,
)


HEAD = "e" * 40


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _rehash_receipt(payload: dict[str, object]) -> None:
    report = payload["report"]
    assert isinstance(report, dict)
    proofs = report["proofs"]
    assert isinstance(proofs, list)
    for proof in proofs:
        assert isinstance(proof, dict)
        proof["digest"] = _digest(
            {
                key: proof[key]
                for key in (
                    "requirement",
                    "subject_id",
                    "source_revision",
                    "passed",
                    "producer_id",
                    "verifier_id",
                    "evidence_refs",
                    "details",
                )
            }
        )
    report["digest"] = _digest(
        {
            "schema_version": report["schema_version"],
            "subject_id": report["subject_id"],
            "source_revision": report["source_revision"],
            "required": report["required"],
            "proof_digests": [
                proof["digest"] for proof in proofs
            ],
            "missing": report["missing"],
            "failed": report["failed"],
            "valid": report["valid"],
        }
    )
    payload["digest"] = _digest(
        {
            "schema_version": payload["schema_version"],
            "source_revision": payload["source_revision"],
            "subject_id": payload["subject_id"],
            "report_digest": report["digest"],
            "primary_result_digest":
                payload["primary_result_digest"],
            "replay_result_digest":
                payload["replay_result_digest"],
            "primary_output_digest":
                payload["primary_output_digest"],
            "replay_output_digest":
                payload["replay_output_digest"],
            "network_attempt_count":
                payload["network_attempt_count"],
            "observed_tool_ids":
                payload["observed_tool_ids"],
            "replay_observed_tool_ids":
                payload["replay_observed_tool_ids"],
            "validity_checks": payload["validity_checks"],
            "valid": payload["valid"],
        }
    )


async def _write_receipt(tmp_path):
    receipt = await qualify_system_completion(
        tmp_path,
        source_revision=HEAD,
    )
    path = tmp_path / "qualification.json"
    path.write_text(
        json.dumps(receipt.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt, path


@pytest.mark.asyncio
async def test_independent_verifier_rehashes_complete_receipt(
    tmp_path,
) -> None:
    receipt, path = await _write_receipt(tmp_path)

    verdict = verify_receipt(path, expected_head=HEAD)

    assert receipt.valid is True
    assert verdict["valid"] is True
    assert verdict["errors"] == []
    assert verdict["receipt_digest"] == receipt.digest
    assert len(verdict["contract_digest"]) == 64
    assert len(verdict["verifier_digest"]) == 64


@pytest.mark.asyncio
async def test_independent_verifier_rejects_tampered_proof_details(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["report"]["proofs"][0]["details"]["tampered"] = True
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    verdict = verify_receipt(path, expected_head=HEAD)

    assert verdict["valid"] is False
    assert any(
        "proof digest mismatch" in error
        for error in verdict["errors"]
    )


@pytest.mark.asyncio
async def test_independent_verifier_rejects_reordered_proofs(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["report"]["proofs"] = list(
        reversed(payload["report"]["proofs"])
    )
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    verdict = verify_receipt(path, expected_head=HEAD)

    assert verdict["valid"] is False
    assert any(
        "canonical requirement order" in error
        for error in verdict["errors"]
    )


@pytest.mark.asyncio
async def test_independent_verifier_rejects_forged_receipt_digest(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["digest"] = "0" * 64
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    verdict = verify_receipt(path, expected_head=HEAD)

    assert verdict["valid"] is False
    assert "qualification receipt digest mismatch" in verdict["errors"]


@pytest.mark.asyncio
async def test_independent_verifier_rejects_semantically_forged_rehashed_proof(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    proofs = payload["report"]["proofs"]
    target = next(
        proof
        for proof in proofs
        if proof["requirement"] == "security.sandbox_filesystem"
    )
    target["details"]["safe_roundtrip"] = False
    target["passed"] = True
    _rehash_receipt(payload)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    verdict = verify_receipt(path, expected_head=HEAD)

    assert verdict["valid"] is False
    assert any(
        "proof semantic pass mismatch: security.sandbox_filesystem"
        in error
        for error in verdict["errors"]
    )


@pytest.mark.asyncio
async def test_independent_verifier_semantically_challenges_all_28_proofs(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)
    baseline = json.loads(path.read_text(encoding="utf-8"))

    mutations = {
        "execution.local_model":
            ("subject_bound", False),
        "execution.offline_isolation":
            ("network_attempt_count", 1),
        "execution.request_result_binding":
            ("result_operation_id", "different-operation"),
        "execution.budget_bounds":
            ("observed_model_turns", 999),
        "execution.stop_semantics":
            ("deadline_fenced", False),
        "execution.tool_authority":
            ("all_calls_authorized", False),
        "execution.durable_recovery":
            ("exact_match", False),
        "execution.staged_finalization_recovery":
            ("intent_cleared", False),
        "execution.replay_lineage":
            ("parent_linked", False),
        "execution.reproducibility":
            ("result_equal", False),
        "execution.governed_effects":
            ("verified_postcondition_count", 1),
        "verification.independent":
            ("policy_satisfied", False),
        "verification.claim_binding":
            ("receipt_context_digest", "0" * 64),
        "context.integrity":
            ("problem_count", 1),
        "memory.lifecycle":
            ("absent_after_delete", False),
        "finalization.lineage":
            ("artifact_ref_count", 0),
        "learning.promotion":
            ("failed_evaluation_rejected", False),
        "learning.rollback":
            ("rollback_without_promotion_rejected", False),
        "security.sandbox_filesystem":
            ("traversal_rejected", False),
        "security.sandbox_process":
            ("network_fail_closed", False),
        "security.injection_sanitization":
            ("duplicate_json_rejected", False),
        "privacy.provider_fallback":
            ("all_within_boundary", False),
        "memory.poisoning_resistance":
            ("conflicting_replay_rejected", False),
        "security.outbound_network_boundary":
            ("peer_rebinding_rejected", False),
        "resource.admission_quota":
            ("over_quota_rejected", False),
        "resource.shared_pressure":
            ("second_worker_blocked", False),
        "execution.idempotent_retry":
            ("no_double_reservation", False),
        "privacy.tenant_isolation":
            ("cross_tenant_get_rejected", False),
    }
    assert set(mutations) == set(
        baseline["report"]["required"]
    )

    for requirement, (field, value) in mutations.items():
        payload = deepcopy(baseline)
        target = next(
            proof
            for proof in payload["report"]["proofs"]
            if proof["requirement"] == requirement
        )
        assert target["passed"] is True
        target["details"][field] = value
        _rehash_receipt(payload)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        verdict = verify_receipt(path, expected_head=HEAD)

        assert verdict["valid"] is False, requirement
        assert any(
            f"proof semantic pass mismatch: {requirement}" in error
            for error in verdict["errors"]
        ), (requirement, verdict)


@pytest.mark.asyncio
async def test_independent_verifier_rejects_wrong_head(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)

    verdict = verify_receipt(
        path,
        expected_head="f" * 40,
    )

    assert verdict["valid"] is False
    assert "not exact-head" in verdict["errors"][0]


@pytest.mark.asyncio
async def test_independent_verifier_rejects_duplicate_json_keys(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)
    encoded = path.read_text(encoding="utf-8")
    needle = f'"source_revision": "{HEAD}"'
    encoded = encoded.replace(
        needle,
        f'{needle},\n  "source_revision": "{HEAD}"',
        1,
    )
    path.write_text(encoded, encoding="utf-8")

    verdict = verify_receipt(path, expected_head=HEAD)

    assert verdict["valid"] is False
    assert "duplicate JSON object key" in verdict["errors"][0]
