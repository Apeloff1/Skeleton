from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.quota import TenantQuota
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger
from skeleton.provider_runtime import (
    OpenAIProviderAdapter,
    OpenAISyncProviderAdapter,
    ProviderProtocolViolationError,
    ProviderRequest,
)


class _SyncResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _limit: int) -> bytes:
        return self._payload


def _runtime(path) -> tuple[AdmissionRuntime, SqliteTenantQuotaLedger]:
    ledger = SqliteTenantQuotaLedger(path)
    ledger.configure(
        "tenant-a",
        TenantQuota(
            window_id="provider-billing",
            max_operations=20,
            max_input_tokens=100_000,
            max_output_tokens=100_000,
            max_cost_usd=100.0,
            max_tool_calls=100,
            max_artifact_bytes=100 * 1024 * 1024,
            max_storage_bytes=100 * 1024 * 1024,
            max_concurrent_operations=4,
        ),
    )
    return AdmissionRuntime(quota_ledger=ledger), ledger


def _request(operation_id: str) -> ProviderRequest:
    return ProviderRequest(
        instructions="answer safely",
        prompt="return a billed response",
        max_output_tokens=64,
        tenant_id="tenant-a",
        operation_id=operation_id,
        estimated_cost_usd=0.5,
    )


def _payload(
    *,
    usage: dict[str, object],
    **extra: object,
) -> dict[str, object]:
    return {
        "id": "resp-billed",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "billed answer",
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": 12,
            "output_tokens": 4,
            "total_tokens": 16,
            **usage,
        },
        **extra,
    }


def _sync_adapter(runtime: AdmissionRuntime) -> OpenAISyncProviderAdapter:
    return OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        admission_runtime=runtime,
    )


def test_explicit_usage_billed_usd_overrides_estimated_cost(
    tmp_path,
    monkeypatch,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")

    def fake_urlopen(_request, timeout):
        assert timeout == 5
        return _SyncResponse(
            _payload(
                usage={
                    "billed_cost": "0.75",
                    "currency": "USD",
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    response = _sync_adapter(runtime).generate_sync(
        _request("provider-billed-usd")
    )

    assert response.usage.estimated_cost == "0.5"
    assert response.usage.billed_cost == "0.75"
    assert response.usage.currency == "USD"
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["completions"] == 1
    assert snapshot["unknown_usage_events"] == 0
    assert snapshot["committed"]["cost_usd"] == pytest.approx(0.75)


def test_usage_cost_usd_is_treated_as_explicit_usd_billing(
    tmp_path,
    monkeypatch,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _SyncResponse(
            _payload(usage={"cost_usd": "0.80"})
        ),
    )

    response = _sync_adapter(runtime).generate_sync(
        _request("provider-cost-usd")
    )

    assert response.usage.billed_cost == "0.80"
    assert response.usage.currency == "USD"
    assert ledger.snapshot("tenant-a")["committed"]["cost_usd"] == pytest.approx(
        0.80
    )


def test_response_level_cost_usd_is_used_when_usage_only_has_tokens(
    tmp_path,
    monkeypatch,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _SyncResponse(
            _payload(
                usage={},
                cost_usd="0.65",
            )
        ),
    )

    response = _sync_adapter(runtime).generate_sync(
        _request("provider-response-cost-usd")
    )

    assert response.usage.billed_cost == "0.65"
    assert response.usage.currency == "USD"
    assert ledger.snapshot("tenant-a")["committed"]["cost_usd"] == pytest.approx(
        0.65
    )


@pytest.mark.parametrize(
    ("usage", "match"),
    [
        (
            {
                "cost_usd": "0.60",
                "billed_cost": "0.70",
                "currency": "USD",
            },
            "conflicting billed cost metadata",
        ),
        (
            {
                "billed_cost": "0.60",
                "currency": "EUR",
            },
            "currency is unsupported",
        ),
        (
            {
                "billed_cost": "0.60",
            },
            "missing currency",
        ),
        (
            {
                "cost_usd": "-1",
            },
            "usage cost_usd is invalid",
        ),
        (
            {
                "cost_usd": "NaN",
            },
            "usage cost_usd is invalid",
        ),
    ],
)
def test_invalid_or_ambiguous_billing_is_quarantined_after_dispatch(
    tmp_path,
    monkeypatch,
    usage,
    match,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _SyncResponse(
            _payload(usage=usage)
        ),
    )

    with pytest.raises(
        ProviderProtocolViolationError,
        match=match,
    ):
        _sync_adapter(runtime).generate_sync(
            _request("provider-billing-invalid")
        )

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["completions"] == 0
    assert snapshot["unknown_usage_events"] == 1
    assert snapshot["usage_events"] == 1
    assert runtime.snapshot()["unknown_usage_operations"] == (
        "provider-billing-invalid",
    )


def test_matching_duplicate_billing_fields_are_accepted(
    tmp_path,
    monkeypatch,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _SyncResponse(
            _payload(
                usage={
                    "cost_usd": "0.700",
                    "billed_cost": "0.7",
                    "currency": "usd",
                },
                cost_usd="0.70",
            )
        ),
    )

    response = _sync_adapter(runtime).generate_sync(
        _request("provider-billing-equal")
    )

    assert response.usage.billed_cost == "0.700"
    assert response.usage.currency == "USD"
    assert ledger.snapshot("tenant-a")["committed"]["cost_usd"] == pytest.approx(
        0.7
    )


class _AsyncResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="resp-async-billed",
            status="completed",
            output_text="async billed answer",
            output=[],
            usage=SimpleNamespace(
                input_tokens=7,
                output_tokens=3,
                total_tokens=10,
                billed_cost="0.66",
                currency="USD",
            ),
        )


class _AsyncClient:
    def __init__(self) -> None:
        self.responses = _AsyncResponses()


@pytest.mark.asyncio
async def test_async_provider_reconciles_explicit_billed_cost(
    tmp_path,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")
    client = _AsyncClient()
    adapter = OpenAIProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        client=client,
        admission_runtime=runtime,
    )

    response = await adapter.generate(_request("provider-async-billed"))

    assert response.usage.billed_cost == "0.66"
    assert response.usage.currency == "USD"
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["completions"] == 1
    assert snapshot["committed"]["cost_usd"] == pytest.approx(0.66)


def test_absent_billing_preserves_estimate_fallback(
    tmp_path,
    monkeypatch,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _SyncResponse(
            _payload(usage={})
        ),
    )

    response = _sync_adapter(runtime).generate_sync(
        _request("provider-estimate-fallback")
    )

    assert response.usage.billed_cost is None
    assert response.usage.estimated_cost == "0.5"
    assert ledger.snapshot("tenant-a")["committed"]["cost_usd"] == pytest.approx(
        0.5
    )
