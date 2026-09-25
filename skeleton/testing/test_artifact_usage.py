from __future__ import annotations

import pytest

from skeleton.artifact_plane.usage import ArtifactUsageMeter
from skeleton.intelligence.admission import (
    AdmissionError,
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.quota import TenantQuota, TenantQuotaLedger


def _runtime(*, max_artifact_bytes: int = 128) -> tuple[
    AdmissionRuntime,
    TenantQuotaLedger,
]:
    ledger = TenantQuotaLedger()
    ledger.configure(
        "tenant-a",
        TenantQuota(
            window_id="window-1",
            max_operations=10,
            max_input_tokens=10_000,
            max_output_tokens=10_000,
            max_cost_usd=100.0,
            max_tool_calls=100,
            max_artifact_bytes=max_artifact_bytes,
            max_concurrent_operations=4,
        ),
    )
    runtime = AdmissionRuntime(quota_ledger=ledger)
    runtime.admit(
        AdmissionRequest(
            operation_id="op-artifact",
            tenant_id="tenant-a",
            capability="artifact-write",
            budget=ResourceBudget(
                max_artifact_bytes=max_artifact_bytes,
            ),
            estimate=UsageEstimate(),
        ),
        now_wall=10.0,
    )
    return runtime, ledger


def test_storage_meter_records_deterministic_category_and_bytes() -> None:
    runtime, ledger = _runtime()
    meter = ArtifactUsageMeter(runtime)

    first = meter.meter_storage(
        "op-artifact",
        "conversation-store",
        "write-1",
        32,
        now_wall=10.1,
    )
    replay = meter.meter_storage(
        "op-artifact",
        "conversation-store",
        "write-1",
        32,
        now_wall=10.2,
    )

    assert replay == first
    assert first.event_id.startswith("storage-")
    assert first.category == "storage"
    assert first.delta.artifact_bytes == 32

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["usage_events"] == 1
    assert snapshot["metered_by_category"]["storage"]["artifact_bytes"] == 32
    assert snapshot["projected"]["artifact_bytes"] == 32


def test_storage_meter_enforces_shared_byte_budget_before_growth() -> None:
    runtime, ledger = _runtime(max_artifact_bytes=64)
    meter = ArtifactUsageMeter(runtime)

    meter.meter_storage(
        "op-artifact",
        "result-store",
        "write-1",
        48,
        now_wall=10.1,
    )

    with pytest.raises(
        AdmissionError,
        match="operation_budget_exceeded:artifact_bytes",
    ):
        meter.meter_storage(
            "op-artifact",
            "result-store",
            "write-2",
            17,
            now_wall=10.2,
        )

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["usage_events"] == 1
    assert snapshot["metered_by_category"]["storage"]["artifact_bytes"] == 48


def test_unknown_storage_usage_blocks_completion_until_resolved() -> None:
    runtime, ledger = _runtime()
    meter = ArtifactUsageMeter(runtime)

    marker = meter.mark_unknown(
        "op-artifact",
        "storage",
        "conversation-store",
        "write-unknown",
        "storage backend did not report bytes",
        now_wall=10.1,
    )

    assert marker.category == "storage"
    assert ledger.snapshot("tenant-a")["unknown_usage_events"] == 1

    resolved = meter.resolve_unknown(
        "op-artifact",
        "storage",
        "conversation-store",
        "write-unknown",
        24,
        now_wall=10.2,
    )
    assert resolved.category == "storage"
    assert resolved.delta.artifact_bytes == 24

    completion = runtime.complete(
        "op-artifact",
        UsageEstimate(),
        now_wall=10.3,
    )
    assert completion.quota_completion is not None
    assert completion.quota_completion.actual.artifact_bytes == 24
    assert ledger.snapshot("tenant-a")["unknown_usage_events"] == 0
