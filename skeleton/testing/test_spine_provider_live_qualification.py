from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from skeleton.persistence.spine_provider_live_qualification import (
    SpineProviderLiveQualification,
    SpineProviderLiveQualificationError,
)
from skeleton.persistence.spine_provider_live_qualification_verify import (
    SpineProviderLiveQualificationVerify,
    SpineProviderLiveQualificationVerifyError,
)
from skeleton.persistence.spine_provider_surface_qualification_verify import (
    SpineProviderSurfaceQualificationVerify,
)


HEAD = "a" * 40
NOW = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _closure() -> dict[str, object]:
    evidence = {
        "head_sha": HEAD,
        "canonical_receipt_digest": "1" * 64,
        "independent_receipt_digest": "2" * 64,
        "declared_digest": "3" * 64,
        "independent_declared_surface_digest": "4" * 64,
        "discovered_digest": "5" * 64,
        "declared_count": 1,
        "discovered_count": 1,
        "scanned_python_files": 2,
        "exact_head": True,
        "independent_agreement": True,
        "provider_surface_closure_green": True,
        "provider_surface_live_green": False,
        "provider_surface_green": False,
        "pr_automation_green": False,
    }
    return {
        "kind": "spine_provider_surface_qualification",
        "hit": True,
        "law": "paired-exact-head-receipts-qualify-provider-closure",
        "citation": "VOL-134",
        **evidence,
        "digest": _digest(evidence),
        "stored_prose": 0,
        "completion_checkbox": False,
        "implementation_signature": False,
        "verification_signature": False,
    }


def _closure_verify() -> dict[str, object]:
    return SpineProviderSurfaceQualificationVerify().verify(_closure())


def _receipt() -> dict[str, object]:
    return {
        "kind": "spine_provider_live_receipt",
        "authority_domain": "provider-live",
        "decision": "qualify-live-provider",
        "head_sha": HEAD,
        "closure_digest": _closure()["digest"],
        "provider_id": "openai",
        "provider_family": "runtime_model",
        "model": "test-model",
        "operation_id": "op-live-1",
        "request_id": "req-live-1",
        "response_id": "resp-live-1",
        "request_digest": "d" * 64,
        "response_digest": "e" * 64,
        "architecture_digest": "f" * 64,
        "latency_ms": 42,
        "issued_at": (NOW - timedelta(seconds=5)).isoformat(),
        "expires_at": (NOW + timedelta(seconds=60)).isoformat(),
        "success": True,
        "network_transport_used": True,
        "credential_boundary_used": True,
        "architecture_acknowledged": True,
        "attestation_digest": "1" * 64,
    }


def test_authenticated_live_call_qualifies_provider_surface() -> None:
    card = SpineProviderLiveQualification().qualify(
        closure=_closure(),
        closure_verify=_closure_verify(),
        receipt=_receipt(),
        expected_head_sha=HEAD,
        authenticate=lambda receipt: receipt["attestation_digest"] == "1" * 64,
        now=NOW,
    )
    verified = SpineProviderLiveQualificationVerify().verify(card)

    assert card["provider_surface_closure_green"] is True
    assert card["provider_surface_live_green"] is True
    assert card["provider_surface_green"] is True
    assert card["attestation_digest"] == "1" * 64
    assert card["pr_automation_green"] is False
    assert card["merge_authority"] is False
    assert verified["verified"] is True


def test_live_provider_receipt_must_be_authenticated_and_fresh() -> None:
    with pytest.raises(
        SpineProviderLiveQualificationError,
        match="not externally authenticated",
    ):
        SpineProviderLiveQualification().qualify(
            closure=_closure(),
            closure_verify=_closure_verify(),
            receipt=_receipt(),
            expected_head_sha=HEAD,
            authenticate=lambda receipt: False,
            now=NOW,
        )

    expired = _receipt()
    expired["expires_at"] = (NOW - timedelta(seconds=1)).isoformat()
    with pytest.raises(
        SpineProviderLiveQualificationError,
        match="expired or invalid",
    ):
        SpineProviderLiveQualification().qualify(
            closure=_closure(),
            closure_verify=_closure_verify(),
            receipt=expired,
            expected_head_sha=HEAD,
            authenticate=lambda receipt: True,
            now=NOW,
        )


def test_live_provider_verifier_rejects_attestation_detachment() -> None:
    card = SpineProviderLiveQualification().qualify(
        closure=_closure(),
        closure_verify=_closure_verify(),
        receipt=_receipt(),
        expected_head_sha=HEAD,
        authenticate=lambda receipt: True,
        now=NOW,
    )
    tampered = copy.deepcopy(card)
    tampered["attestation_digest"] = "2" * 64
    with pytest.raises(
        SpineProviderLiveQualificationVerifyError,
        match="digest mismatch",
    ):
        SpineProviderLiveQualificationVerify().verify(tampered)


def test_live_provider_verifier_rejects_merge_authority_tamper() -> None:
    card = SpineProviderLiveQualification().qualify(
        closure=_closure(),
        closure_verify=_closure_verify(),
        receipt=_receipt(),
        expected_head_sha=HEAD,
        authenticate=lambda receipt: True,
        now=NOW,
    )
    tampered = copy.deepcopy(card)
    tampered["merge_authority"] = True
    with pytest.raises(
        SpineProviderLiveQualificationVerifyError,
        match="overclaimed merge authority",
    ):
        SpineProviderLiveQualificationVerify().verify(tampered)



def test_live_provider_verifier_rejects_invalid_validity_window() -> None:
    card = SpineProviderLiveQualification().qualify(
        closure=_closure(),
        closure_verify=_closure_verify(),
        receipt=_receipt(),
        expected_head_sha=HEAD,
        authenticate=lambda receipt: True,
        now=NOW,
    )
    tampered = copy.deepcopy(card)
    tampered["valid_until"] = tampered["issued_at"]
    evidence = {
        key: value
        for key, value in tampered.items()
        if key
        not in {
            "kind",
            "hit",
            "law",
            "citation",
            "digest",
            "stored_prose",
            "completion_checkbox",
            "implementation_signature",
            "verification_signature",
        }
    }
    tampered["digest"] = _digest(evidence)
    with pytest.raises(
        SpineProviderLiveQualificationVerifyError,
        match="validity window is invalid",
    ):
        SpineProviderLiveQualificationVerify().verify(tampered)
