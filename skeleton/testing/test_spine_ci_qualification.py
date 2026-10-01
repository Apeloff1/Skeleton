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


HEAD = "a" * 40


def _policy_digest(checks: list[str]) -> str:
    payload = {
        "schema_version": 1,
        "required_checks": checks,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _receipt() -> dict[str, object]:
    checks = [
        "Backend Quality",
        "P2 Repository Engineering Control",
        "Provider Surface Closure Gate",
        "Repository Hygiene Gate",
        "State Recovery Drill",
        "Workflow Input Security",
    ]
    return {
        "kind": "spine_ci_exact_head_receipt",
        "authority_domain": "ci-exact-head",
        "head_sha": HEAD,
        "required_check_policy_digest": _policy_digest(checks),
        "required_check_count": len(checks),
        "checks": [
            {
                "name": name,
                "head_sha": HEAD,
                "run_id": index + 100,
                "run_attempt": 1,
                "conclusion": "success",
            }
            for index, name in enumerate(checks)
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
