from __future__ import annotations

import hashlib
import sqlite3

import pytest

from skeleton.ai.runtime.observability.cost_governor import (
    CostGovernor,
    CostGovernorConflict,
    CostGovernorError,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.quota import TenantQuota


def _quota() -> TenantQuota:
    return TenantQuota(
        window_id="unknown-usage-reattach",
        max_operations=100,
        max_input_tokens=100_000,
        max_output_tokens=100_000,
        max_cost_usd=100.0,
        max_tool_calls=100,
        max_artifact_bytes=10_000_000,
        max_storage_bytes=10_000_000,
        max_concurrent_operations=8,
    )


def _request(operation_id: str) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability="model-inference",
        budget=ResourceBudget(
            max_input_tokens=10_000,
            max_output_tokens=5_000,
            max_cost_usd=5.0,
            max_wall_seconds=60.0,
            max_provider_attempts=4,
            max_tool_calls=20,
            max_artifact_bytes=1_000_000,
            max_storage_bytes=1_000_000,
            max_concurrency=4,
            max_queue_depth=100,
        ),
        estimate=UsageEstimate(
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.5,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
    )


def _evidence(label: str) -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source=f"test:unknown-usage-reattach:{label}",
            digest=hashlib.sha256(label.encode("utf-8")).hexdigest(),
            category="unknown_usage_reattach",
        ),
    )


def _governor(path) -> CostGovernor:
    return CostGovernor.durable(
        path,
        default_tenant_quota=_quota(),
    )


def test_unknown_usage_is_visible_immediately_after_restart(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    operation = "op-unknown-restart"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        "provider-unknown",
        "provider",
        "provider omitted terminal usage",
        now_wall=11.0,
    )

    restarted = _governor(path)
    restarted.reserve(_request(operation), now_wall=20.0)

    snapshot = restarted.runtime.snapshot()
    assert snapshot["unknown_usage_events"] == 1
    assert snapshot["unknown_usage_operations"] == (operation,)
    assert restarted.runtime.telemetry_snapshot()["metrics"]["counters"][
        "admission.unknown_usage_reattached_total"
    ] == 1

    with pytest.raises(
        CostGovernorError,
        match="actual_usage_unknown:provider",
    ):
        restarted.complete(
            operation,
            UsageEstimate(),
            evidence_refs=_evidence("blocked"),
            now_wall=21.0,
        )


def test_replaying_original_unknown_reason_rehydrates_local_marker(
    tmp_path,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    operation = "op-unknown-reason"
    reason = "provider returned output without final accounting"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)
    original = first.mark_usage_unknown(
        operation,
        "provider-unknown",
        "provider",
        reason,
        now_wall=11.0,
    )

    restarted = _governor(path)
    restarted.reserve(_request(operation), now_wall=20.0)
    replay = restarted.mark_usage_unknown(
        operation,
        "provider-unknown",
        "provider",
        reason,
        now_wall=21.0,
    )

    assert replay.reason == reason
    assert replay.recorded_at == original.recorded_at
    assert restarted.runtime.snapshot()["unknown_usage_events"] == 1
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "unknown_usage_events"
    ] == 1


def test_resolve_recovered_unknown_usage_then_complete(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    operation = "op-unknown-resolve"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        "provider-unknown",
        "provider",
        "terminal provider usage unavailable",
        now_wall=11.0,
    )

    restarted = _governor(path)
    restarted.reserve(_request(operation), now_wall=20.0)
    charge = restarted.resolve_unknown_usage(
        operation,
        "provider-unknown",
        UsageEstimate(
            input_tokens=80,
            output_tokens=15,
            cost_usd=0.4,
        ),
        now_wall=21.0,
    )

    assert charge.resolved_unknown_usage is True
    assert restarted.runtime.snapshot()["unknown_usage_events"] == 0
    assert restarted.runtime.snapshot()["unknown_usage_operations"] == ()
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "unknown_usage_events"
    ] == 0

    decision = restarted.complete(
        operation,
        UsageEstimate(
            input_tokens=80,
            output_tokens=15,
            cost_usd=0.4,
            wall_seconds=3.0,
            provider_attempts=1,
        ),
        evidence_refs=_evidence("resolved"),
        now_wall=22.0,
    )
    assert decision.state == "completed"
    assert decision.accepted is True


def test_multiple_recovered_unknown_markers_remain_independent(
    tmp_path,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    operation = "op-unknown-multiple"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        "provider-unknown",
        "provider",
        "provider accounting pending",
        now_wall=11.0,
    )
    first.mark_usage_unknown(
        operation,
        "tool-unknown",
        "tool",
        "tool accounting pending",
        now_wall=12.0,
    )

    restarted = _governor(path)
    restarted.reserve(_request(operation), now_wall=20.0)
    assert restarted.runtime.snapshot()["unknown_usage_events"] == 2

    restarted.resolve_unknown_usage(
        operation,
        "provider-unknown",
        UsageEstimate(cost_usd=0.2),
        now_wall=21.0,
    )
    assert restarted.runtime.snapshot()["unknown_usage_events"] == 1

    with pytest.raises(
        CostGovernorError,
        match="actual_usage_unknown:tool",
    ):
        restarted.release_unspent(operation)


def test_recovered_unknown_marker_rejects_category_change(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    operation = "op-unknown-category-conflict"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        "ambiguous-event",
        "provider",
        "provider usage pending",
        now_wall=11.0,
    )

    restarted = _governor(path)
    restarted.reserve(_request(operation), now_wall=20.0)

    with pytest.raises(
        CostGovernorConflict,
        match="different inputs",
    ):
        restarted.mark_usage_unknown(
            operation,
            "ambiguous-event",
            "tool",
            "different category",
            now_wall=21.0,
        )

    assert restarted.runtime.snapshot()["unknown_usage_events"] == 1


def test_corrupted_durable_unknown_identity_blocks_reattach(tmp_path) -> None:
    path = tmp_path / "runtime.sqlite3"
    operation = "op-unknown-corrupt"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        "provider-unknown",
        "provider",
        "provider usage pending",
        now_wall=11.0,
    )

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE quota_usage_events
            SET operation_id = ?
            WHERE event_id = ?
            """,
            ("other-operation", "provider-unknown"),
        )

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="durable unknown usage marker identity mismatch",
    ):
        restarted.reserve(_request(operation), now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1
