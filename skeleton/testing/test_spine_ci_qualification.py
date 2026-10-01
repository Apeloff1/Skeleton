from __future__ import annotations

import copy
import hashlib
import json

import pytest

from skeleton.persistence.spine_ci_qualification import (
    SpineCiQualification,
    SpineCiQualificationError,
)
from skeleton.persistence.spine_ci_qualification_verify import (
    SpineCiQualificationVerify,
    SpineCiQualificationVerifyError,
)
from skeleton.persistence.spine_ci_policy import (
    REQUIRED_CHECK_EVENT,
    REQUIRED_CHECK_POLICY_DIGEST,
    REQUIRED_CHECKS,
    REQUIRED_CHECK_WORKFLOWS,
)


HEAD = "a" * 40


def _receipt() -> dict[str, object]:
    return {
        "kind": "spine_ci_exact_head_receipt",
        "authority_domain": "ci-exact-head",
        "head_sha": HEAD,
        "required_check_policy_digest": REQUIRED_CHECK_POLICY_DIGEST,
        "required_check_count": len(REQUIRED_CHECKS),
        "checks": [
            {
                "name": name,
                "head_sha": HEAD,
                "workflow_path": REQUIRED_CHECK_WORKFLOWS[name],
                "event": REQUIRED_CHECK_EVENT,
                "run_id": index + 100,
                "run_attempt": 1,
                "conclusion": "success",
            }
            for index, name in enumerate(REQUIRED_CHECKS)
        ],
        "catalog_complete": True,
        "pending_count": 0,
        "failing_count": 0,
        "missing_count": 0,
        "attestation_digest": "c" * 64,
    }


def test_complete_exact_head_catalog_qualifies_ci_not_merge() -> None:
    card = SpineCiQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        authenticate=lambda receipt: receipt["attestation_digest"] == "c" * 64,
    )
    verified = SpineCiQualificationVerify().verify(card)

    assert card["ci_green"] is True
    assert card["catalog_complete"] is True
    assert card["authority_domain"] == "ci-exact-head"
    assert len(card["checks"]) == 6
    assert card["attestation_digest"] == "c" * 64
    assert card["merge_authority"] is False
    assert verified["verified"] is True
    assert verified["merge_authority"] is False


def test_pending_or_non_exact_check_fails_closed() -> None:
    pending = _receipt()
    pending["pending_count"] = 1
    with pytest.raises(
        SpineCiQualificationError,
        match="nonzero pending_count",
    ):
        SpineCiQualification().qualify(
            receipt=pending,
            expected_head_sha=HEAD,
            authenticate=lambda receipt: True,
        )

    drifted = _receipt()
    drifted["checks"][0]["head_sha"] = "d" * 40
    with pytest.raises(
        SpineCiQualificationError,
        match="not exact-head",
    ):
        SpineCiQualification().qualify(
            receipt=drifted,
            expected_head_sha=HEAD,
            authenticate=lambda receipt: True,
        )


def test_catalog_and_policy_digest_must_match_repository_policy() -> None:
    reduced = _receipt()
    reduced["checks"] = reduced["checks"][:1]
    reduced["required_check_count"] = 1
    with pytest.raises(
        SpineCiQualificationError,
        match="catalog does not match policy",
    ):
        SpineCiQualification().qualify(
            receipt=reduced,
            expected_head_sha=HEAD,
            authenticate=lambda receipt: True,
        )

    forged = _receipt()
    forged["required_check_policy_digest"] = "f" * 64
    with pytest.raises(
        SpineCiQualificationError,
        match="policy digest mismatch",
    ):
        SpineCiQualification().qualify(
            receipt=forged,
            expected_head_sha=HEAD,
            authenticate=lambda receipt: True,
        )


def test_ci_verifier_rejects_policy_catalog_tamper() -> None:
    card = SpineCiQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        authenticate=lambda receipt: True,
    )
    tampered = copy.deepcopy(card)
    tampered["check_names"] = tampered["check_names"][:-1]
    tampered["required_check_count"] -= 1
    with pytest.raises(
        SpineCiQualificationVerifyError,
        match="catalog does not match policy",
    ):
        SpineCiQualificationVerify().verify(tampered)


def test_ci_verifier_reconstructs_exact_check_evidence() -> None:
    card = SpineCiQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        authenticate=lambda receipt: True,
    )
    tampered = copy.deepcopy(card)
    tampered["checks"][0]["head_sha"] = "e" * 40
    with pytest.raises(
        SpineCiQualificationVerifyError,
        match="not exact-head",
    ):
        SpineCiQualificationVerify().verify(tampered)


def test_ci_verifier_rejects_attestation_detachment() -> None:
    card = SpineCiQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        authenticate=lambda receipt: True,
    )
    tampered = copy.deepcopy(card)
    tampered["attestation_digest"] = "d" * 64
    with pytest.raises(
        SpineCiQualificationVerifyError,
        match="digest mismatch",
    ):
        SpineCiQualificationVerify().verify(tampered)


def test_ci_verifier_rejects_merge_authority_tamper() -> None:
    card = SpineCiQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        authenticate=lambda receipt: True,
    )
    tampered = copy.deepcopy(card)
    tampered["merge_authority"] = True
    with pytest.raises(
        SpineCiQualificationVerifyError,
        match="overclaimed merge authority",
    ):
        SpineCiQualificationVerify().verify(tampered)


def test_ci_qualification_rejects_workflow_identity_tamper() -> None:
    receipt = _receipt()
    receipt["checks"][0]["workflow_path"] = (
        ".github/workflows/forged-backend-quality.yml"
    )
    with pytest.raises(
        SpineCiQualificationError,
        match="workflow identity mismatch",
    ):
        SpineCiQualification().qualify(
            receipt=receipt,
            expected_head_sha=HEAD,
            authenticate=lambda candidate: True,
        )


def test_ci_verifier_rejects_workflow_identity_tamper() -> None:
    card = SpineCiQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        authenticate=lambda candidate: True,
    )
    tampered = copy.deepcopy(card)
    tampered["checks"][0]["event"] = "workflow_dispatch"
    with pytest.raises(
        SpineCiQualificationVerifyError,
        match="workflow identity mismatch",
    ):
        SpineCiQualificationVerify().verify(tampered)
