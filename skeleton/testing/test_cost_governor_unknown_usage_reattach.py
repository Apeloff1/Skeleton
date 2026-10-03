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
from skeleton.intelligence.quota import TenantQuota, TenantQuotaLedger
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger


def _quota() -> TenantQuota:
    return TenantQuota(
        window_id="unknown-reattach-window",
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


def _governor(path) -> CostGovernor:
    return CostGovernor.durable(
        path,
        default_tenant_quota=_quota(),
    )


def _evidence(label: str) -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source=f"test:unknown-reattach:{label}",
            digest=hashlib.sha256(label.encode("utf-8")).hexdigest(),
            category="unknown_usage_recovery",
        ),
    )


def test_unknown_usage_marker_rehydrates_after_restart(tmp_path) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-unknown-restart"
    request = _request(operation)
    first = _governor(path)
    first.reserve(request, now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        "provider-unknown-1",
        "provider",
        "provider response omitted usage",
        now_wall=10.5,
    )

    restarted = _governor(path)
    restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.snapshot()["unknown_usage_operations"] == (
        operation,
    )
    counters = restarted.runtime.telemetry_snapshot()["metrics"]["counters"]
    assert counters["admission.reattached_total"] == 1
    assert counters["admission.unknown_usage_reattached_total"] == 1

    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["unknown_usage_events"] == 1


def test_rehydrated_unknown_usage_blocks_release_and_completion(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-unknown-blocks"
    request = _request(operation)
    first = _governor(path)
    first.reserve(request, now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        "provider-unknown-2",
        "provider",
        "provider response ambiguous",
        now_wall=10.5,
    )

    restarted = _governor(path)
    restarted.reserve(request, now_wall=20.0)

    with pytest.raises(
        CostGovernorError,
        match="actual_usage_unknown:provider",
    ):
        restarted.release_unspent(operation)

    with pytest.raises(
        CostGovernorError,
        match="actual_usage_unknown:provider",
    ):
        restarted.complete(
            operation,
            UsageEstimate(
                input_tokens=120,
                output_tokens=25,
                cost_usd=0.7,
                wall_seconds=3.0,
                provider_attempts=1,
            ),
            evidence_refs=_evidence("blocked"),
            now_wall=21.0,
        )

    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["completions"] == 0


def test_rehydrated_marker_resolves_by_original_event_id(tmp_path) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-unknown-resolve"
    event_id = "provider-unknown-3"
    request = _request(operation)
    first = _governor(path)
    first.reserve(request, now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        event_id,
        "provider",
        "provider usage delayed",
        now_wall=10.5,
    )

    restarted = _governor(path)
    restarted.reserve(request, now_wall=20.0)
    charge = restarted.resolve_unknown_usage(
        operation,
        event_id,
        UsageEstimate(
            input_tokens=120,
            output_tokens=25,
            cost_usd=0.7,
        ),
        now_wall=20.5,
    )

    assert charge.event_id == event_id
    assert charge.category == "provider"
    assert charge.resolved_unknown_usage is True
    assert restarted.runtime.snapshot()["unknown_usage_operations"] == ()

    decision = restarted.complete(
        operation,
        UsageEstimate(
            input_tokens=120,
            output_tokens=25,
            cost_usd=0.7,
            wall_seconds=3.0,
            provider_attempts=1,
        ),
        evidence_refs=_evidence("resolved"),
        now_wall=21.0,
    )
    assert decision.state == "completed"

    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["unknown_usage_events"] == 0
    assert snapshot["completions"] == 1


def test_multiple_rehydrated_markers_remain_fenced_until_all_resolved(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-multi-unknown"
    request = _request(operation)
    first = _governor(path)
    first.reserve(request, now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        "provider-unknown-multi",
        "provider",
        "provider usage missing",
        now_wall=10.5,
    )
    first.mark_usage_unknown(
        operation,
        "tool-unknown-multi",
        "tool",
        "tool usage missing",
        now_wall=10.6,
    )

    restarted = _governor(path)
    restarted.reserve(request, now_wall=20.0)
    counters = restarted.runtime.telemetry_snapshot()["metrics"]["counters"]
    assert counters["admission.unknown_usage_reattached_total"] == 2

    restarted.resolve_unknown_usage(
        operation,
        "provider-unknown-multi",
        UsageEstimate(
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.5,
        ),
        now_wall=20.5,
    )
    assert restarted.runtime.snapshot()["unknown_usage_operations"] == (
        operation,
    )

    with pytest.raises(
        CostGovernorError,
        match="actual_usage_unknown:tool",
    ):
        restarted.release_unspent(operation)

    restarted.resolve_unknown_usage(
        operation,
        "tool-unknown-multi",
        UsageEstimate(tool_calls=1),
        now_wall=20.6,
    )
    assert restarted.runtime.snapshot()["unknown_usage_operations"] == ()


def test_tampered_durable_unknown_category_fails_closed(tmp_path) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-tampered-unknown"
    request = _request(operation)
    first = _governor(path)
    first.reserve(request, now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        "provider-unknown-tampered",
        "provider",
        "provider usage missing",
        now_wall=10.5,
    )

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE quota_usage_events
            SET category = 'unknown:unsupported-category'
            WHERE event_id = ?
            """,
            ("provider-unknown-tampered",),
        )

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="durable unknown usage category is invalid",
    ):
        restarted.reserve(request, now_wall=20.0)

    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["completions"] == 0


@pytest.mark.parametrize("durable", [False, True])
def test_atomic_recovery_snapshot_returns_reservation_and_unknown_markers(
    tmp_path,
    durable,
) -> None:
    if durable:
        ledger = SqliteTenantQuotaLedger(tmp_path / "atomic-recovery.sqlite3")
    else:
        ledger = TenantQuotaLedger()
    ledger.configure("tenant-a", _quota())

    request = _request("op-atomic-recovery")
    reservation = ledger.reserve(
        request.tenant_id,
        request.operation_id,
        request.estimate,
        now=10.0,
    )
    marker = ledger.mark_usage_unknown(
        reservation.reservation_id,
        "provider-atomic-unknown",
        "provider",
        now=10.5,
    )

    state = ledger.recovery_state_for_operation(
        request.tenant_id,
        request.operation_id,
    )
    assert state is not None
    recovered_reservation, unresolved = state
    assert recovered_reservation == reservation
    assert unresolved == (marker,)

    assert (
        ledger.recovery_state_for_operation(
            request.tenant_id,
            "missing-operation",
        )
        is None
    )


def test_first_post_restart_marker_replay_restores_reason_once(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-reason-replay"
    event_id = "provider-reason-replay"
    request = _request(operation)
    first = _governor(path)
    first.reserve(request, now_wall=10.0)
    first.mark_usage_unknown(
        operation,
        event_id,
        "provider",
        "original provider usage reason",
        now_wall=10.5,
    )

    restarted = _governor(path)
    restarted.reserve(request, now_wall=20.0)

    replay = restarted.mark_usage_unknown(
        operation,
        event_id,
        "provider",
        "original provider usage reason",
        now_wall=20.5,
    )
    assert replay.reason == "original provider usage reason"

    with pytest.raises(
        CostGovernorConflict,
        match="unknown usage event replayed with different inputs",
    ):
        restarted.mark_usage_unknown(
            operation,
            event_id,
            "provider",
            "different reason after replay identity restored",
            now_wall=21.0,
        )

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "unknown_usage_events"
    ] == 1
