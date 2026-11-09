from __future__ import annotations

import copy
import hashlib
import json

import pytest

from skeleton.persistence.spine_provider_surface_qualification import (
    SpineProviderSurfaceQualification,
    SpineProviderSurfaceQualificationError,
)
from skeleton.persistence.spine_provider_surface_qualification_verify import (
    SpineProviderSurfaceQualificationVerify,
    SpineProviderSurfaceQualificationVerifyError,
)


HEAD = "a" * 40


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _declared() -> list[dict[str, object]]:
    return [
        {
            "id": "runtime",
            "owner": "skeleton/provider_runtime.py",
            "surface_class": "canonical_runtime",
            "credential_owner": True,
            "network_transport_owner": True,
            "sdk_client_owner": True,
        }
    ]


def _canonical() -> dict[str, object]:
    return {
        "schema_version": 1,
        "head_sha": HEAD,
        "declared_surfaces": [
            {
                **_declared()[0],
                "discovery_edge_classes": [
                    "credential",
                    "network_transport",
                    "sdk_client",
                ],
            }
        ],
        "discovered_surfaces": {
            "skeleton/provider_runtime.py": {
                "edge_classes": [
                    "credential",
                    "network_transport",
                    "sdk_client",
                ]
            }
        },
        "application_isolation_surfaces": ["backend/facade.py"],
        "validation_errors": [],
        "valid": True,
    }


def _independent() -> dict[str, object]:
    declared = [{**_declared()[0], "receipt_required": True}]
    payload = [
        {
            "id": row["id"],
            "owner": row["owner"],
            "surface_class": row["surface_class"],
            "credential_owner": row["credential_owner"],
            "network_transport_owner": row["network_transport_owner"],
            "sdk_client_owner": row["sdk_client_owner"],
            "receipt_required": row["receipt_required"],
        }
        for row in declared
    ]
    return {
        "schema_version": 1,
        "verifier": "independent-provider-surface-v1",
        "head_sha": HEAD,
        "scanned_python_files": 2,
        "declared_surface_digest": _digest(payload),
        "declared_surfaces": declared,
        "discovered_provider_edges": [
            {
                "path": "skeleton/provider_runtime.py",
                "edge_classes": [
                    "credential",
                    "network_transport",
                    "sdk_client",
                ],
            }
        ],
        "errors": [],
        "valid": True,
    }


def test_paired_exact_head_receipts_qualify_closure_not_live_health() -> None:
    qualifier = SpineProviderSurfaceQualification()
    canonical = qualifier.canonical_summary(_canonical())
    independent = qualifier.independent_summary(_independent())

    card = qualifier.qualify(
        canonical=canonical,
        independent=independent,
        expected_head_sha=HEAD,
    )
    verified = SpineProviderSurfaceQualificationVerify().verify(card)

    assert card["provider_surface_closure_green"] is True
    assert card["provider_surface_live_green"] is False
    assert card["provider_surface_green"] is False
    assert card["pr_automation_green"] is False
    assert verified["verified"] is True


def test_provider_qualification_rejects_head_or_ownership_drift() -> None:
    qualifier = SpineProviderSurfaceQualification()
    canonical = qualifier.canonical_summary(_canonical())

    wrong_head = _independent()
    wrong_head["head_sha"] = "b" * 40
    independent = qualifier.independent_summary(wrong_head)
    with pytest.raises(
        SpineProviderSurfaceQualificationError,
        match="not exact-head",
    ):
        qualifier.qualify(
            canonical=canonical,
            independent=independent,
            expected_head_sha=HEAD,
        )

    drifted = _independent()
    drifted["declared_surfaces"][0]["owner"] = "backend/rogue.py"
    independent = qualifier.independent_summary(drifted)
    with pytest.raises(
        SpineProviderSurfaceQualificationError,
        match="declared_digest",
    ):
        qualifier.qualify(
            canonical=canonical,
            independent=independent,
            expected_head_sha=HEAD,
        )


def test_provider_verifier_rejects_forged_live_green() -> None:
    qualifier = SpineProviderSurfaceQualification()
    card = qualifier.qualify(
        canonical=qualifier.canonical_summary(_canonical()),
        independent=qualifier.independent_summary(_independent()),
        expected_head_sha=HEAD,
    )
    forged = copy.deepcopy(card)
    forged["provider_surface_live_green"] = True
    with pytest.raises(
        SpineProviderSurfaceQualificationVerifyError,
        match="overclaimed",
    ):
        SpineProviderSurfaceQualificationVerify().verify(forged)
