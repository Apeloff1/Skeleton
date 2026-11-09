from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from skeleton.intelligence.admission_runtime import (
    AdmissionRuntime,
    AdmissionRuntimeError,
)
from skeleton.intelligence.quota import TenantQuota
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger
from skeleton.provider_runtime import (
    OpenAIProviderAdapter,
    OpenAISyncProviderAdapter,
    ProviderImageRequest,
    ProviderInvocationError,
    ProviderRequest,
    ProviderUnavailableError,
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
            window_id="provider-accounting",
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
        prompt="hello provider",
        max_output_tokens=64,
        tenant_id="tenant-a",
        operation_id=operation_id,
        estimated_cost_usd=0.5,
    )


def test_successful_sync_provider_call_persists_usage_event_before_completion(
    tmp_path,
    monkeypatch,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")

    def fake_urlopen(_request, timeout):
        assert timeout == 5
        return _SyncResponse(
            {
                "id": "resp-accounted",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "accounted answer",
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 4,
                    "total_tokens": 16,
                },
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        admission_runtime=runtime,
    )

    response = adapter.generate_sync(_request("provider-accounted"))

    assert response.text == "accounted answer"
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["completions"] == 1
    assert snapshot["usage_events"] == 1
    assert snapshot["committed"]["input_tokens"] == 12
    assert snapshot["committed"]["output_tokens"] == 4
    assert snapshot["committed"]["cost_usd"] == pytest.approx(0.5)
    assert runtime.snapshot()["unknown_usage_events"] == 0


def test_ambiguous_sync_dispatch_failure_is_quarantined_durably(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "quota.sqlite3"
    runtime, ledger = _runtime(path)

    def fail_after_dispatch(*_args, **_kwargs):
        raise URLError("transport outcome unknown")

    monkeypatch.setattr("urllib.request.urlopen", fail_after_dispatch)
    adapter = OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        admission_runtime=runtime,
    )

    with pytest.raises(
        ProviderInvocationError,
        match="model provider request failed",
    ):
        adapter.generate_sync(_request("provider-ambiguous"))

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["unknown_usage_events"] == 1
    assert runtime.snapshot()["unknown_usage_operations"] == (
        "provider-ambiguous",
    )

    with pytest.raises(
        AdmissionRuntimeError,
        match="actual_usage_unknown:provider",
    ):
        runtime.release("provider-ambiguous")

    restarted = SqliteTenantQuotaLedger(path)
    restarted_snapshot = restarted.snapshot("tenant-a")
    assert restarted_snapshot["active_reservations"] == 1
    assert restarted_snapshot["unknown_usage_events"] == 1


def test_pre_dispatch_sync_failure_releases_reservation_without_unknown_spend(
    tmp_path,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")
    adapter = OpenAISyncProviderAdapter(
        api_key="",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        admission_runtime=runtime,
    )

    with pytest.raises(
        ProviderUnavailableError,
        match="OPENAI_API_KEY is not configured",
    ):
        adapter.generate_sync(_request("provider-pre-dispatch"))

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["unknown_usage_events"] == 0
    assert snapshot["usage_events"] == 0


class _BadImages:
    async def generate(self, **_kwargs):
        return SimpleNamespace(
            id="bad-image",
            data=[
                SimpleNamespace(
                    b64_json="not-base64",
                    revised_prompt=None,
                )
            ],
        )


class _AsyncClient:
    def __init__(self) -> None:
        self.images = _BadImages()
        self.responses = SimpleNamespace()
        self.audio = SimpleNamespace()


@pytest.mark.asyncio
async def test_post_dispatch_media_protocol_failure_is_quarantined(
    tmp_path,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")
    adapter = OpenAIProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        client=_AsyncClient(),
        admission_runtime=runtime,
    )

    with pytest.raises(
        ProviderInvocationError,
        match="invalid base64 payload",
    ):
        await adapter.generate_image(
            ProviderImageRequest(
                prompt="bounded image request",
                operation_id="image-ambiguous",
                tenant_id="tenant-a",
                estimated_cost_usd=0.25,
            )
        )

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["unknown_usage_events"] == 1
    assert runtime.snapshot()["unknown_usage_operations"] == (
        "image-ambiguous",
    )


@pytest.mark.asyncio
async def test_default_nonquota_media_failure_keeps_compatibility_release() -> None:
    runtime = AdmissionRuntime()
    adapter = OpenAIProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
        client=_AsyncClient(),
        admission_runtime=runtime,
    )

    with pytest.raises(
        ProviderInvocationError,
        match="invalid base64 payload",
    ):
        await adapter.generate_image(
            ProviderImageRequest(
                prompt="bounded image request",
                operation_id="image-no-quota",
            )
        )

    assert runtime.snapshot()["active_operations"] == ()
    assert runtime.snapshot()["unknown_usage_events"] == 0
