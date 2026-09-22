from __future__ import annotations

import pytest

from skeleton.vault.data_governance import (
    DataClass,
    DataGovernanceDenied,
    ProviderTransferRequest,
    evaluate_provider_transfer,
    require_provider_transfer,
)


@pytest.mark.parametrize(
    ("raw", "expected", "routing"),
    [
        ("public", DataClass.PUBLIC, "public"),
        ("internal", DataClass.INTERNAL, "private"),
        ("confidential", DataClass.CONFIDENTIAL, "sensitive"),
        ("restricted", DataClass.RESTRICTED, "local-only"),
        (0, DataClass.PUBLIC, "public"),
        (3, DataClass.RESTRICTED, "local-only"),
    ],
)
def test_data_class_parsing_and_routing_privacy(raw, expected, routing) -> None:
    parsed = DataClass.parse(raw)

    assert parsed is expected
    assert parsed.routing_privacy == routing


@pytest.mark.parametrize("raw", ["unknown", -1, 99, True, object()])
def test_unknown_data_class_fails_closed(raw) -> None:
    with pytest.raises(DataGovernanceDenied, match="unknown data classification"):
        DataClass.parse(raw)


def test_internal_provider_transfer_is_permitted_for_declared_purpose() -> None:
    decision = require_provider_transfer(
        ProviderTransferRequest(
            provider_id="openai",
            data_class="internal",
            purpose="model-inference",
            source="test",
        )
    )

    assert decision.permitted is True
    assert decision.provider_id == "openai"
    assert decision.data_class == "internal"
    assert decision.routing_privacy == "private"
    assert decision.reason_code == "baseline_policy_permits"
    assert decision.tenant_bound is False
    assert decision.decision_id.startswith("gov-")


def test_restricted_provider_transfer_is_denied() -> None:
    decision = evaluate_provider_transfer(
        ProviderTransferRequest(
            provider_id="openai",
            data_class="restricted",
            purpose="model-inference",
            tenant_id="tenant-secret",
            source="test",
        )
    )

    assert decision.permitted is False
    assert decision.reason_code == "restricted_external_transfer_denied"
    assert decision.routing_privacy == "local-only"

    with pytest.raises(
        DataGovernanceDenied,
        match="restricted_external_transfer_denied",
    ):
        require_provider_transfer(
            ProviderTransferRequest(
                provider_id="openai",
                data_class="restricted",
                purpose="model-inference",
                tenant_id="tenant-secret",
                source="test",
            )
        )


def test_confidential_transfer_requires_tenant_binding() -> None:
    denied = evaluate_provider_transfer(
        ProviderTransferRequest(
            provider_id="openai",
            data_class="confidential",
            purpose="retrieval-synthesis",
            source="test",
        )
    )
    permitted = require_provider_transfer(
        ProviderTransferRequest(
            provider_id="openai",
            data_class="confidential",
            purpose="retrieval-synthesis",
            tenant_id="tenant-123",
            source="test",
        )
    )

    assert denied.permitted is False
    assert denied.reason_code == "confidential_requires_tenant"
    assert permitted.permitted is True
    assert permitted.tenant_bound is True
    assert permitted.routing_privacy == "sensitive"


def test_unknown_transfer_purpose_is_denied() -> None:
    decision = evaluate_provider_transfer(
        ProviderTransferRequest(
            provider_id="openai",
            data_class="public",
            purpose="side-channel",
            source="test",
        )
    )

    assert decision.permitted is False
    assert decision.reason_code == "purpose_not_allowed"


def test_decision_id_is_deterministic_but_contains_no_payload() -> None:
    request = ProviderTransferRequest(
        provider_id="openai",
        data_class="confidential",
        purpose="code-assistance",
        tenant_id="tenant-123",
        source="backend",
    )

    first = require_provider_transfer(request)
    second = require_provider_transfer(request)

    assert first.decision_id == second.decision_id
    serialized = str(first.as_dict())
    assert "prompt" not in serialized
    assert "secret payload" not in serialized
    assert len(first.decision_id) == 28


def test_normalization_bounds_identifiers() -> None:
    with pytest.raises(DataGovernanceDenied, match="provider_id is required"):
        require_provider_transfer(
            ProviderTransferRequest(provider_id="", data_class="public")
        )

    with pytest.raises(DataGovernanceDenied, match="tenant_id is too long"):
        require_provider_transfer(
            ProviderTransferRequest(
                provider_id="openai",
                data_class="confidential",
                tenant_id="x" * 257,
            )
        )
