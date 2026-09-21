from __future__ import annotations

import pytest

from skeleton.intelligence.admission import UsageEstimate
from skeleton.intelligence.quota import (
    QuotaConflict,
    QuotaError,
    QuotaExceeded,
    TenantQuota,
    TenantQuotaLedger,
)


def _ledger(
    *,
    max_operations: int = 10,
    max_input_tokens: int = 10_000,
    max_output_tokens: int = 5_000,
    max_cost_usd: float = 10.0,
    max_concurrent: int = 2,
) -> TenantQuotaLedger:
    ledger = TenantQuotaLedger()
    ledger.configure(
        "tenant-a",
        TenantQuota(
            window_id="2026-09-21",
            max_operations=max_operations,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            max_cost_usd=max_cost_usd,
            max_concurrent_operations=max_concurrent,
        ),
    )
    return ledger


def test_reservation_is_idempotent_for_same_operation_and_estimate() -> None:
    ledger = _ledger()
    estimate = UsageEstimate(input_tokens=100, output_tokens=50, cost_usd=0.1)

    first = ledger.reserve("tenant-a", "op-1", estimate, now=10.0)
    second = ledger.reserve("tenant-a", "op-1", estimate, now=20.0)

    assert first == second
    assert first.reservation_id.startswith("qrs-")
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["reserved"]["operations"] == 1


def test_same_operation_with_different_estimate_conflicts() -> None:
    ledger = _ledger()
    ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(input_tokens=100),
        now=10.0,
    )

    with pytest.raises(QuotaConflict, match="different estimate"):
        ledger.reserve(
            "tenant-a",
            "op-1",
            UsageEstimate(input_tokens=101),
            now=11.0,
        )


def test_projected_reservations_count_against_cumulative_quota() -> None:
    ledger = _ledger(max_input_tokens=150)
    ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(input_tokens=100),
        now=10.0,
    )

    with pytest.raises(QuotaExceeded, match="input_tokens"):
        ledger.reserve(
            "tenant-a",
            "op-2",
            UsageEstimate(input_tokens=51),
            now=11.0,
        )


def test_concurrency_limit_rejects_third_active_operation() -> None:
    ledger = _ledger(max_concurrent=2)
    ledger.reserve("tenant-a", "op-1", UsageEstimate(), now=10.0)
    ledger.reserve("tenant-a", "op-2", UsageEstimate(), now=11.0)

    with pytest.raises(QuotaExceeded, match="tenant_concurrency_exceeded"):
        ledger.reserve("tenant-a", "op-3", UsageEstimate(), now=12.0)


def test_release_returns_capacity_without_committing_usage() -> None:
    ledger = _ledger(max_concurrent=1)
    reservation = ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(input_tokens=100, cost_usd=1.0),
        now=10.0,
    )

    released = ledger.release(reservation.reservation_id)
    snapshot = ledger.snapshot("tenant-a")

    assert released == reservation
    assert snapshot["active_reservations"] == 0
    assert snapshot["committed"]["input_tokens"] == 0
    assert snapshot["committed"]["cost_usd"] == 0.0


def test_completion_reconciles_actual_usage_not_estimate() -> None:
    ledger = _ledger()
    reservation = ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(input_tokens=100, output_tokens=50, cost_usd=0.5),
        now=10.0,
    )

    completion = ledger.complete(
        reservation.reservation_id,
        UsageEstimate(input_tokens=80, output_tokens=30, cost_usd=0.25),
        now=11.0,
    )
    snapshot = ledger.snapshot("tenant-a")

    assert completion.overrun is False
    assert snapshot["committed"]["input_tokens"] == 80
    assert snapshot["committed"]["output_tokens"] == 30
    assert snapshot["committed"]["cost_usd"] == 0.25
    assert snapshot["reserved"]["input_tokens"] == 0
    assert snapshot["active_reservations"] == 0


def test_actual_usage_overrun_is_recorded_not_hidden() -> None:
    ledger = _ledger(max_cost_usd=1.0)
    reservation = ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(cost_usd=0.5),
        now=10.0,
    )

    completion = ledger.complete(
        reservation.reservation_id,
        UsageEstimate(cost_usd=1.25),
        now=11.0,
    )

    assert completion.overrun is True
    assert completion.overrun_dimensions == ("cost_usd",)
    assert ledger.snapshot("tenant-a")["over_quota_dimensions"] == ["cost_usd"]


def test_completed_operation_cannot_be_reserved_again() -> None:
    ledger = _ledger()
    estimate = UsageEstimate(input_tokens=10)
    reservation = ledger.reserve("tenant-a", "op-1", estimate, now=10.0)
    ledger.complete(reservation.reservation_id, estimate, now=11.0)

    with pytest.raises(QuotaConflict, match="already completed"):
        ledger.reserve("tenant-a", "op-1", estimate, now=12.0)


def test_window_reset_requires_no_active_reservations_and_new_window() -> None:
    ledger = _ledger()
    reservation = ledger.reserve("tenant-a", "op-1", UsageEstimate(), now=10.0)

    with pytest.raises(QuotaConflict, match="active"):
        ledger.reset_window(
            "tenant-a",
            TenantQuota(window_id="2026-09-22"),
        )

    ledger.release(reservation.reservation_id)

    with pytest.raises(QuotaConflict, match="must change"):
        ledger.reset_window(
            "tenant-a",
            TenantQuota(window_id="2026-09-21"),
        )

    ledger.reset_window(
        "tenant-a",
        TenantQuota(window_id="2026-09-22"),
    )
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["window_id"] == "2026-09-22"
    assert snapshot["committed"]["operations"] == 0


def test_unknown_tenant_and_reservation_fail_closed() -> None:
    ledger = _ledger()

    with pytest.raises(QuotaError, match="not configured"):
        ledger.reserve("tenant-b", "op", UsageEstimate())

    with pytest.raises(QuotaError, match="unknown active"):
        ledger.release("qrs-does-not-exist")


def test_quota_snapshot_contains_no_operation_payload() -> None:
    ledger = _ledger()
    ledger.reserve(
        "tenant-a",
        "op-1",
        UsageEstimate(input_tokens=10),
        now=10.0,
    )

    rendered = str(ledger.snapshot("tenant-a"))
    assert "prompt" not in rendered
    assert "secret" not in rendered
