from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.artifact_plane.usage import ArtifactUsageMeter
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    RuntimePressure,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import (
    AdmissionRuntime,
    AdmissionRuntimeError,
)
from skeleton.intelligence.quota import QuotaExceeded, TenantQuota
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger


def _quota() -> TenantQuota:
    return TenantQuota(
        window_id="artifact-window-1",
        max_operations=10,
        max_input_tokens=10_000,
        max_output_tokens=10_000,
        max_cost_usd=100.0,
        max_tool_calls=100,
        max_artifact_bytes=10_000,
        max_concurrent_operations=10,
    )


def _request(
    operation_id: str,
    *,
    max_artifact_bytes: int = 1024,
) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability="artifact-build",
        budget=ResourceBudget(
            max_input_tokens=100,
            max_output_tokens=100,
            max_cost_usd=1.0,
            max_wall_seconds=30.0,
            max_provider_attempts=1,
            max_tool_calls=4,
            max_artifact_bytes=max_artifact_bytes,
            max_concurrency=4,
            max_queue_depth=20,
        ),
        estimate=UsageEstimate(),
        pressure=RuntimePressure(),
    )


def _runtime(
    path: Path,
    *,
    configure: bool,
) -> tuple[AdmissionRuntime, SqliteTenantQuotaLedger]:
    ledger = SqliteTenantQuotaLedger(path)
    if configure:
        ledger.configure("tenant-a", _quota())
    return AdmissionRuntime(quota_ledger=ledger), ledger


def test_artifact_and_storage_actual_bytes_reconcile_into_same_budget(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    runtime, ledger = _runtime(path, configure=True)
    runtime.admit(_request("op-artifact"), now_wall=10.0)
    meter = ArtifactUsageMeter(runtime)

    artifact = meter.meter_artifact(
        "op-artifact",
        "artifact-1",
        "write-1",
        400,
        now_wall=11.0,
    )
    storage = meter.meter_storage(
        "op-artifact",
        "storage-1",
        "write-1",
        200,
        now_wall=12.0,
    )

    assert artifact.category == "artifact"
    assert artifact.delta.artifact_bytes == 400
    assert storage.category == "storage"
    assert storage.delta.artifact_bytes == 200

    completion = runtime.complete(
        "op-artifact",
        UsageEstimate(),
        now_wall=13.0,
    )
    assert completion.quota_completion is not None
    assert completion.quota_completion.actual.artifact_bytes == 600

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["committed"]["artifact_bytes"] == 600
    assert snapshot["active_reservations"] == 0


def test_artifact_usage_replay_survives_runtime_restart(tmp_path: Path) -> None:
    path = tmp_path / "quota.sqlite3"
    first, _ = _runtime(path, configure=True)
    request = _request("op-restart")
    first.admit(request, now_wall=10.0)
    first_meter = ArtifactUsageMeter(first)
    event = first_meter.meter_artifact(
        "op-restart",
        "artifact-1",
        "write-1",
        300,
        now_wall=11.0,
    )

    restarted, ledger = _runtime(path, configure=False)
    restarted.admit(request, now_wall=20.0)
    restarted_meter = ArtifactUsageMeter(restarted)
    replay = restarted_meter.meter_artifact(
        "op-restart",
        "artifact-1",
        "write-1",
        300,
        now_wall=99.0,
    )

    assert replay == event
    completion = restarted.complete(
        "op-restart",
        UsageEstimate(),
        now_wall=21.0,
    )
    assert completion.quota_completion is not None
    assert completion.quota_completion.actual.artifact_bytes == 300
    assert ledger.snapshot("tenant-a")["committed"]["artifact_bytes"] == 300


def test_artifact_meter_rejects_actual_bytes_above_operation_budget_before_growth(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    runtime, ledger = _runtime(path, configure=True)
    runtime.admit(
        _request("op-budget", max_artifact_bytes=500),
        now_wall=10.0,
    )
    meter = ArtifactUsageMeter(runtime)

    meter.meter_artifact(
        "op-budget",
        "artifact-1",
        "write-1",
        400,
        now_wall=11.0,
    )
    with pytest.raises(
        Exception,
        match="operation_budget_exceeded:artifact_bytes",
    ):
        meter.meter_storage(
            "op-budget",
            "storage-1",
            "write-1",
            101,
            now_wall=12.0,
        )

    assert runtime.snapshot()["active_operations"] == ("op-budget",)
    quota_snapshot = ledger.snapshot("tenant-a")
    assert quota_snapshot["metered_by_category"]["artifact"][
        "artifact_bytes"
    ] == 400
    assert "storage" not in quota_snapshot["metered_by_category"]


def test_unknown_artifact_size_survives_restart_and_blocks_completion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    first, _ = _runtime(path, configure=True)
    request = _request("op-unknown")
    first.admit(request, now_wall=10.0)
    first_meter = ArtifactUsageMeter(first)
    marker = first_meter.mark_unknown(
        "op-unknown",
        "artifact",
        "artifact-unknown",
        "write-unknown",
        "compressed_size_unknown",
        now_wall=11.0,
    )
    assert marker.category == "artifact"

    restarted, ledger = _runtime(path, configure=False)
    restarted.admit(request, now_wall=20.0)

    with pytest.raises(
        AdmissionRuntimeError,
        match="actual_usage_unknown:artifact",
    ):
        restarted.complete(
            "op-unknown",
            UsageEstimate(),
            now_wall=21.0,
        )

    meter = ArtifactUsageMeter(restarted)
    resolved = meter.resolve_unknown(
        "op-unknown",
        "artifact",
        "artifact-unknown",
        "write-unknown",
        512,
        now_wall=22.0,
    )
    assert resolved.category == "artifact"
    assert resolved.delta.artifact_bytes == 512

    completion = restarted.complete(
        "op-unknown",
        UsageEstimate(),
        now_wall=23.0,
    )
    assert completion.quota_completion is not None
    assert completion.quota_completion.actual.artifact_bytes == 512
    assert ledger.snapshot("tenant-a")["unknown_usage_events"] == 0


def test_artifact_meter_requires_one_existing_admission_lease(
    tmp_path: Path,
) -> None:
    runtime, _ = _runtime(tmp_path / "quota.sqlite3", configure=True)
    meter = ArtifactUsageMeter(runtime)

    with pytest.raises(Exception, match="operation has no active admission lease"):
        meter.meter_artifact(
            "missing-operation",
            "artifact-1",
            "write-1",
            1,
        )
