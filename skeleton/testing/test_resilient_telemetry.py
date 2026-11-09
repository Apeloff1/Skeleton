from __future__ import annotations

import json

import pytest

from skeleton.observability.redaction import REDACTED
from skeleton.observability.resilient_telemetry import (
    ResilientTelemetry,
    ResilientTelemetryError,
)


def test_sink_outage_never_breaks_core_event_path() -> None:
    def broken(_event):
        raise RuntimeError("collector unavailable")

    telemetry = ResilientTelemetry(sink=broken)
    result = telemetry.emit(
        "operation.accepted",
        payload={"operation_id": "op-1"},
        correlation_id="trace-1",
    )

    assert result.delivered is False
    assert result.sink_failed is True
    assert telemetry.sink_failures == 1
    reconstructed = telemetry.reconstruct()
    assert reconstructed["receipt_count"] == 1
    assert reconstructed["by_kind"] == {"operation.accepted": 1}


def test_cardinality_bomb_collapses_new_series_after_bound() -> None:
    telemetry = ResilientTelemetry(max_series=3)

    for index in range(50):
        telemetry.emit(
            "request",
            labels={"tenant": f"tenant-{index}"},
            payload={"index": index},
        )

    assert telemetry.series_count == 3
    assert telemetry.overflow_events == 47
    reconstructed = telemetry.reconstruct()
    assert reconstructed["overflow_events_in_window"] == 47
    assert reconstructed["receipt_count"] == 50


def test_sensitive_values_are_redacted_before_sink_and_digest_ledger() -> None:
    observed = []
    telemetry = ResilientTelemetry(sink=observed.append)
    secret = "super-secret-token"

    telemetry.emit(
        "auth.failure",
        labels={"authorization": f"Bearer {secret}", "route": "/api"},
        payload={
            "api_key": secret,
            "message": f"authorization: Bearer {secret}",
            "nested": {"password": secret},
        },
    )

    assert len(observed) == 1
    event = observed[0]
    assert event["labels"]["authorization"] == REDACTED
    assert event["payload"]["api_key"] == REDACTED
    assert event["payload"]["nested"]["password"] == REDACTED
    assert secret not in json.dumps(event, sort_keys=True)
    assert secret not in json.dumps(telemetry.reconstruct(), sort_keys=True)


def test_reconstruction_survives_complete_sink_failure_without_payload_prose() -> None:
    telemetry = ResilientTelemetry(sink=lambda _event: (_ for _ in ()).throw(OSError("down")))

    telemetry.emit("operation.accepted", correlation_id="trace-a")
    telemetry.emit("operation.completed", correlation_id="trace-a")
    telemetry.emit("operation.accepted", correlation_id="trace-b")

    report = telemetry.reconstruct()
    assert report["sink_failures_total"] == 3
    assert report["by_kind"] == {
        "operation.accepted": 2,
        "operation.completed": 1,
    }
    assert report["first_sequence"] == 1
    assert report["last_sequence"] == 3
    assert len(report["receipt_digests"]) == 3
    assert all(len(item) == 64 for item in report["receipt_digests"])


def test_reconstruction_ledger_is_bounded_and_preserves_sequence_window() -> None:
    telemetry = ResilientTelemetry(max_receipts=3)

    for index in range(6):
        telemetry.emit("tick", payload={"index": index})

    rows = telemetry.receipts()
    assert [item.sequence for item in rows] == [4, 5, 6]
    report = telemetry.reconstruct()
    assert report["receipt_count"] == 3
    assert report["first_sequence"] == 4
    assert report["last_sequence"] == 6


def test_existing_series_remains_usable_after_cardinality_saturation() -> None:
    telemetry = ResilientTelemetry(max_series=1)
    first = telemetry.emit("request", labels={"tenant": "a"})
    again = telemetry.emit("request", labels={"tenant": "a"})
    overflow = telemetry.emit("request", labels={"tenant": "b"})

    assert first.receipt.overflowed is False
    assert again.receipt.overflowed is False
    assert again.receipt.series_id == first.receipt.series_id
    assert overflow.receipt.overflowed is True
    assert telemetry.series_count == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_series": 0},
        {"max_series": True},
        {"max_receipts": 0},
        {"max_labels": -1},
    ],
)
def test_invalid_bounds_fail_fast(kwargs) -> None:
    with pytest.raises(ResilientTelemetryError):
        ResilientTelemetry(**kwargs)


def test_non_finite_payload_and_clock_fail_closed() -> None:
    telemetry = ResilientTelemetry()
    with pytest.raises(ResilientTelemetryError, match="finite canonical JSON"):
        telemetry.emit("bad", payload={"value": float("nan")})

    telemetry = ResilientTelemetry(clock=lambda: float("inf"))
    with pytest.raises(ResilientTelemetryError, match="non-finite"):
        telemetry.emit("bad-clock")


def test_label_count_is_bounded_before_series_allocation() -> None:
    telemetry = ResilientTelemetry(max_labels=1)
    with pytest.raises(ResilientTelemetryError, match="label count"):
        telemetry.emit("request", labels={"a": 1, "b": 2})
    assert telemetry.series_count == 0
    assert telemetry.receipts() == ()
