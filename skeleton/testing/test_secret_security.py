from __future__ import annotations

import pytest

from skeleton.ai.runtime.security.secret_handles import (
    SecretGrant,
    SecretRef,
    SecretSecurityError,
    SecretUseReceipt,
    evaluate_secret_use,
    sanitize_secret_metadata,
)


def _ref(handle: str = "secret-handle-1") -> SecretRef:
    return SecretRef(
        handle_id=handle,
        provider_id="vault-primary",
        version_id="version-7",
    )


def _grant(
    *,
    handle: str = "secret-handle-1",
    consumer: str = "model-router",
    scopes: tuple[str, ...] = ("provider.call", "provider.read"),
    expires: int = 2_000,
) -> SecretGrant:
    return SecretGrant(
        grant_id="grant-1",
        handle_id=handle,
        consumer_id=consumer,
        scopes=scopes,
        expires_at_ns=expires,
    )


def test_secret_reference_is_opaque_and_content_addressable() -> None:
    ref = _ref()

    assert ref.handle_id == "secret-handle-1"
    assert ref.provider_id == "vault-primary"
    assert ref.version_id == "version-7"
    assert len(ref.digest) == 64
    assert not hasattr(ref, "value")
    assert not hasattr(ref, "secret")


def test_secret_grant_is_scope_bound_and_expires() -> None:
    grant = _grant(scopes=("provider.read", "provider.call"))

    assert grant.scopes == ("provider.call", "provider.read")
    assert grant.permits("provider.call", now_ns=1_999) is True
    assert grant.permits("provider.write", now_ns=1_999) is False
    assert grant.permits("provider.call", now_ns=2_000) is False


@pytest.mark.parametrize(
    ("ref_handle", "grant_handle", "consumer", "scope", "now_ns", "reason"),
    (
        ("secret-handle-2", "secret-handle-1", "model-router", "provider.call", 10, "handle-mismatch"),
        ("secret-handle-1", "secret-handle-1", "other-consumer", "provider.call", 10, "consumer-mismatch"),
        ("secret-handle-1", "secret-handle-1", "model-router", "provider.call", 2_000, "grant-expired"),
        ("secret-handle-1", "secret-handle-1", "model-router", "provider.write", 10, "scope-denied"),
    ),
)
def test_secret_use_denials_fail_closed(
    ref_handle: str,
    grant_handle: str,
    consumer: str,
    scope: str,
    now_ns: int,
    reason: str,
) -> None:
    receipt = evaluate_secret_use(
        receipt_id=f"receipt-{reason}",
        secret_ref=_ref(ref_handle),
        grant=_grant(handle=grant_handle),
        consumer_id=consumer,
        scope=scope,
        operation_id="operation-1",
        now_ns=now_ns,
    )

    assert receipt.allowed is False
    assert receipt.reason_code == reason
    assert receipt.secret_material_present is False


def test_secret_use_allows_only_matching_live_grant() -> None:
    receipt = evaluate_secret_use(
        receipt_id="receipt-allowed",
        secret_ref=_ref(),
        grant=_grant(),
        consumer_id="model-router",
        scope="provider.call",
        operation_id="operation-1",
        now_ns=1_000,
    )

    assert receipt.allowed is True
    assert receipt.reason_code == "allowed"
    assert receipt.handle_id == "secret-handle-1"
    assert receipt.consumer_id == "model-router"
    assert receipt.secret_material_present is False
    assert len(receipt.digest) == 64


def test_secret_use_receipt_rejects_secret_material_flag() -> None:
    with pytest.raises(SecretSecurityError, match="cannot carry secret material"):
        SecretUseReceipt(
            receipt_id="receipt-bad",
            grant_id="grant-1",
            handle_id="secret-handle-1",
            consumer_id="model-router",
            scope="provider.call",
            operation_id="operation-1",
            allowed=True,
            reason_code="allowed",
            used_at_ns=1,
            secret_material_present=True,
        )


def test_secret_metadata_redacts_nested_secret_shaped_fields() -> None:
    payload = {
        "provider": "secondary",
        "authorization": "Bearer example-credential",
        "nested": {
            "api-key": "example-api-key",
            "password": "example-password",
            "token_count": 123,
        },
        "items": [
            {"refresh_token": "example-refresh"},
            {"safe": "visible"},
        ],
    }

    sanitized, findings = sanitize_secret_metadata(payload)

    assert sanitized == {
        "provider": "secondary",
        "authorization": "[REDACTED]",
        "nested": {
            "api-key": "[REDACTED]",
            "password": "[REDACTED]",
            "token_count": 123,
        },
        "items": [
            {"refresh_token": "[REDACTED]"},
            {"safe": "visible"},
        ],
    }
    assert findings == (
        "$.authorization",
        "$.items[0].refresh_token",
        "$.nested.api-key",
        "$.nested.password",
    )
    evidence_text = repr((sanitized, findings))
    for raw in (
        "Bearer example-credential",
        "example-api-key",
        "example-password",
        "example-refresh",
    ):
        assert raw not in evidence_text


def test_secret_metadata_rejects_bytes_and_cycles() -> None:
    with pytest.raises(SecretSecurityError, match="cannot contain bytes"):
        sanitize_secret_metadata({"payload": b"not-json"})

    cyclic: dict[str, object] = {}
    cyclic["child"] = cyclic
    with pytest.raises(SecretSecurityError, match="cannot contain cycles"):
        sanitize_secret_metadata(cyclic)


def test_secret_contracts_reject_unbounded_or_empty_identity() -> None:
    with pytest.raises(SecretSecurityError, match="non-empty"):
        SecretRef(handle_id="", provider_id="vault", version_id="v1")
    with pytest.raises(SecretSecurityError, match="maximum length"):
        SecretRef(handle_id="h" * 257, provider_id="vault", version_id="v1")
    with pytest.raises(SecretSecurityError, match="scopes must be non-empty"):
        _grant(scopes=())


def test_secret_redaction_findings_are_input_order_independent() -> None:
    first = {
        "password": "example-password",
        "nested": {"api_key": "example-api-key"},
    }
    second = {
        "nested": {"api_key": "example-api-key"},
        "password": "example-password",
    }

    first_sanitized, first_findings = sanitize_secret_metadata(first)
    second_sanitized, second_findings = sanitize_secret_metadata(second)

    assert first_sanitized == second_sanitized
    assert first_findings == second_findings == (
        "$.nested.api_key",
        "$.password",
    )
