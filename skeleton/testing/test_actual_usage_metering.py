from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.artifact_plane.usage import ArtifactUsageMeter
from skeleton.intelligence.admission import (
    AdmissionError,
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import (
    AdmissionRuntime,
    AdmissionRuntimeError,
)
from skeleton.intelligence.quota import TenantQuota
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger
from skeleton.skills.usage import SkillUsageMeter


def _runtime(path: Path) -> tuple[AdmissionRuntime, SqliteTenantQuotaLedger]:
    ledger = SqliteTenantQuotaLedger(path)
    try:
        ledger.configure(
            "tenant-a",
            TenantQuota(
                window_id="window-1",
                max_operations=20,
                max_input_tokens=100_000,
                max_output_tokens=100_000,
                max_cost_usd=100.0,
                max_tool_calls=20,
                max_artifact_bytes=10_000,
                max_concurrent_operations=4,
            ),
        )
    except Exception as exc:
        if "already configured" not in str(exc):
            raise
    return AdmissionRuntime(quota_ledger=ledger), ledger


def _request(
    operation_id: str,
    *,
    max_tool_calls: int = 4,
    max_artifact_bytes: int = 1_000,
    max_storage_bytes: int = 1_000,
) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability="build-work",
        budget=ResourceBudget(
            max_input_tokens=10_000,
            max_output_tokens=10_000,
            max_cost_usd=10.0,
            max_wall_seconds=60.0,
            max_provider_attempts=3,
            max_tool_calls=max_tool_calls,
            max_artifact_bytes=max_artifact_bytes,
            max_storage_bytes=max_storage_bytes,
            max_concurrency=4,
            max_queue_depth=100,
        ),
        estimate=UsageEstimate(),
    )


def test_skill_execution_retry_is_idempotent_and_commits_actual_usage(
    tmp_path: Path,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")
    runtime.admit(_request("op-skill"), now_wall=10.0)
    meter = SkillUsageMeter(runtime)

    first = meter.meter_execution(
        "op-skill",
        "repo-search",
        "attempt-1",
        now_wall=10.1,
    )
    replay = meter.meter_execution(
        "op-skill",
        "repo-search",
        "attempt-1",
        now_wall=99.0,
    )

    assert replay.event_id == first.event_id
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["usage_events"] == 1
    assert snapshot["metered_by_category"]["tool"]["tool_calls"] == 1

    completion = runtime.complete(
        "op-skill",
        UsageEstimate(),
        now_wall=11.0,
    )
    assert completion.quota_completion is not None
    assert completion.quota_completion.actual.tool_calls == 1


def test_artifact_and_storage_bytes_use_independent_monotonic_budgets(
    tmp_path: Path,
) -> None:
    runtime, ledger = _runtime(tmp_path / "quota.sqlite3")
    runtime.admit(
        _request(
            "op-artifact",
            max_artifact_bytes=300,
            max_storage_bytes=180,
        ),
        now_wall=10.0,
    )
    meter = ArtifactUsageMeter(runtime)

    meter.meter_artifact(
        "op-artifact",
        "report",
        "render-1",
        120,
        now_wall=10.1,
    )
    meter.meter_storage(
        "op-artifact",
        "report",
        "persist-1",
        150,
        now_wall=10.2,
    )

    with pytest.raises(AdmissionError, match="operation_budget_exceeded:storage_bytes"):
        meter.meter_storage(
            "op-artifact",
            "report",
            "persist-2",
            31,
            now_wall=10.3,
        )

    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["reserved"]["artifact_bytes"] == 120
    assert snapshot["reserved"]["storage_bytes"] == 150
    assert snapshot["metered_by_category"]["artifact"]["artifact_bytes"] == 120
    assert snapshot["metered_by_category"]["storage"]["storage_bytes"] == 150

    completion = runtime.complete(
        "op-artifact",
        UsageEstimate(),
        now_wall=11.0,
    )
    assert completion.quota_completion is not None
    assert completion.quota_completion.actual.artifact_bytes == 120
    assert completion.quota_completion.actual.storage_bytes == 150


def test_unknown_usage_survives_runtime_restart_and_blocks_completion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    first_runtime, _ = _runtime(path)
    request = _request("op-unknown")
    first_runtime.admit(request, now_wall=10.0)
    meter = SkillUsageMeter(first_runtime)
    marker = meter.mark_unknown(
        "op-unknown",
        "external-tool",
        "attempt-1",
        "tool returned no usage receipt",
        now_wall=10.5,
    )

    restarted_ledger = SqliteTenantQuotaLedger(path)
    restarted_runtime = AdmissionRuntime(quota_ledger=restarted_ledger)
    restarted_runtime.admit(request, now_wall=20.0)

    assert restarted_ledger.snapshot("tenant-a")["unknown_usage_events"] == 1
    with pytest.raises(AdmissionRuntimeError, match="actual_usage_unknown:tool"):
        restarted_runtime.complete(
            "op-unknown",
            UsageEstimate(),
            now_wall=20.5,
        )

    resolved = restarted_runtime.resolve_unknown_usage(
        "op-unknown",
        marker.event_id,
        UsageEstimate(tool_calls=1),
        now_wall=21.0,
    )
    assert resolved.category == "tool"
    assert restarted_ledger.snapshot("tenant-a")["unknown_usage_events"] == 0

    completion = restarted_runtime.complete(
        "op-unknown",
        UsageEstimate(),
        now_wall=22.0,
    )
    assert completion.quota_completion is not None
    assert completion.quota_completion.actual.tool_calls == 1


def test_unknown_storage_usage_can_only_resolve_inside_operation_budget(
    tmp_path: Path,
) -> None:
    runtime, _ = _runtime(tmp_path / "quota.sqlite3")
    runtime.admit(
        _request(
            "op-unknown-artifact",
            max_artifact_bytes=100,
            max_storage_bytes=100,
        ),
        now_wall=10.0,
    )
    meter = ArtifactUsageMeter(runtime)
    meter.mark_unknown(
        "op-unknown-artifact",
        "storage",
        "blob",
        "write-1",
        "remote store omitted content length",
        now_wall=10.1,
    )

    with pytest.raises(AdmissionError, match="operation_budget_exceeded:storage_bytes"):
        meter.resolve_unknown(
            "op-unknown-artifact",
            "storage",
            "blob",
            "write-1",
            101,
            now_wall=10.2,
        )

    assert runtime.snapshot()["unknown_usage_events"] == 1
