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
    ProviderPolicyError,
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
            window_id="provider-success-usage-fencing",
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
        prompt="return a response",
        max_output_tokens=64,
        tenant_id="tenant-a",
        operation_id=operation_id,
        estimated_cost_usd=0.5,
    )


def _payload(usage: object = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "resp-usage-fence",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "bounded answer",
                    }
                ],
            }
        ],
    }
    if usage is not None:
        payload["usage"] = usage
    return payload


@pytest.mark.parametrize(
    ("usage", "missing"),
    [
        (None, "input_tokens,output_tokens"),
        ({"input_tokens": 12}, "output_tokens"),
        ({"output_tokens": 4}, "input_tokens"),
        (
            {
                "input_tokens": -1,
                "output_tokens": 4,
            },
            "input_tokens",
        ),
        (
            {
                "input_tokens": 12,
                "output_tokens": "invalid",
            },
            "output_tokens",
        ),
        (
            {
                "billed_cost": "0.7",
                "currency": "USD",
            },
            "input_tokens,output_tokens",
        ),
    ],
)
def test_durable_sync_success_with_incomplete_token_usage_is_quarantined(
    tmp_path,
    monkeypatch,
    usage,
    missing,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _SyncResponse(_payload(usage)),
    )
    adapter = OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        admission_runtime=runtime,
    )

    with pytest.raises(
        ProviderPolicyError,
        match=f"usage metadata incomplete:{missing}",
    ):
        adapter.generate_sync(_request("sync-usage-incomplete"))

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["completions"] == 0
    assert snapshot["unknown_usage_events"] == 1
    assert snapshot["usage_events"] == 1
    assert runtime.snapshot()["unknown_usage_operations"] == (
        "sync-usage-incomplete",
    )
    counters = runtime.telemetry_snapshot()["metrics"]["counters"]
    assert counters["provider.unknown_usage_quarantined_total"] == 1
    assert "provider.unknown_usage_marker_error_total" not in counters


def test_durable_sync_complete_provider_usage_reconciles_normally(
    tmp_path,
    monkeypatch,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _SyncResponse(
            _payload(
                {
                    "input_tokens": 12,
                    "output_tokens": 4,
                    "total_tokens": 16,
                }
            )
        ),
    )
    adapter = OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        admission_runtime=runtime,
    )

    response = adapter.generate_sync(_request("sync-usage-complete"))

    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 4
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["completions"] == 1
    assert snapshot["unknown_usage_events"] == 0


def test_nonquota_sync_runtime_keeps_estimate_compatibility(
    monkeypatch,
) -> None:
    runtime = AdmissionRuntime()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _SyncResponse(_payload()),
    )
    adapter = OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        admission_runtime=runtime,
    )

    response = adapter.generate_sync(_request("sync-no-quota"))

    assert response.text == "bounded answer"
    assert response.usage.input_tokens is None
    assert response.usage.output_tokens is None
    assert runtime.snapshot()["active_operations"] == ()


class _AsyncResponses:
    def __init__(self, usage) -> None:
        self.usage = usage

    async def create(self, **_kwargs):
        return SimpleNamespace(
            id="resp-async-usage-fence",
            status="completed",
            output_text="async bounded answer",
            output=[],
            usage=self.usage,
        )


class _AsyncClient:
    def __init__(self, usage) -> None:
        self.responses = _AsyncResponses(usage)


@pytest.mark.asyncio
async def test_durable_async_success_with_partial_usage_is_quarantined(
    tmp_path,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")
    adapter = OpenAIProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        client=_AsyncClient(
            SimpleNamespace(
                input_tokens=7,
                output_tokens=None,
                total_tokens=None,
            )
        ),
        admission_runtime=runtime,
    )

    with pytest.raises(
        ProviderPolicyError,
        match="usage metadata incomplete:output_tokens",
    ):
        await adapter.generate(_request("async-usage-incomplete"))

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["completions"] == 0
    assert snapshot["unknown_usage_events"] == 1


@pytest.mark.asyncio
async def test_nonquota_async_runtime_keeps_estimate_compatibility() -> None:
    runtime = AdmissionRuntime()
    adapter = OpenAIProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        client=_AsyncClient(None),
        admission_runtime=runtime,
    )

    response = await adapter.generate(_request("async-no-quota"))

    assert response.text == "async bounded answer"
    assert response.usage.input_tokens is None
    assert response.usage.output_tokens is None
    assert runtime.snapshot()["active_operations"] == ()
