from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from skeleton.observability.integrity import (
    IntegrityStatus,
    ObservabilityIntegrityConflict,
    ObservabilityIntegrityMonitor,
    TelemetryReceiptObservation,
    TelemetrySourcePolicy,
)
from skeleton.observability.resilient_telemetry import ResilientTelemetry


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def obs(seq: int, *, delivered: bool = True, series: str = "a"):
    return TelemetryReceiptObservation(
        source="runtime",
        sequence=seq,
        event_digest=digest(f"event-{seq}"),
        series_id=digest(series),
        delivered=delivered,
    )


class ObservabilityIntegrityTests(unittest.TestCase):
    def test_missing_and_stale_heartbeat_are_unknown(self) -> None:
        monitor = ObservabilityIntegrityMonitor(
            (TelemetrySourcePolicy("runtime", heartbeat_timeout_ticks=2, critical=True),)
        )
        self.assertEqual(monitor.report().status, IntegrityStatus.UNKNOWN)
        monitor.heartbeat("runtime")
        self.assertEqual(monitor.report().status, IntegrityStatus.UNKNOWN)
        monitor.observe(obs(1))
        self.assertEqual(monitor.report().status, IntegrityStatus.HEALTHY)
        monitor.advance(3)
        self.assertEqual(monitor.report().status, IntegrityStatus.UNKNOWN)

    def test_contiguous_delivery_is_healthy_and_gap_is_breached(self) -> None:
        monitor = ObservabilityIntegrityMonitor(
            (TelemetrySourcePolicy("runtime", max_sequence_gap=0),)
        )
        monitor.observe(obs(1))
        monitor.observe(obs(2))
        self.assertEqual(monitor.report().status, IntegrityStatus.HEALTHY)
        monitor.observe(obs(4))
        source = monitor.report().sources[0]
        self.assertEqual(source.status, IntegrityStatus.BREACHED)
        self.assertEqual(source.sequence_gap_total, 1)
        self.assertEqual(source.lost, 1)

    def test_sequence_replay_is_identity_bound(self) -> None:
        monitor = ObservabilityIntegrityMonitor((TelemetrySourcePolicy("runtime"),))
        item = obs(1)
        monitor.observe(item)
        monitor.observe(item)
        with self.assertRaises(ObservabilityIntegrityConflict):
            monitor.observe(
                TelemetryReceiptObservation(
                    source="runtime",
                    sequence=1,
                    event_digest=digest("changed"),
                    series_id=digest("a"),
                    delivered=True,
                )
            )

    def test_loss_and_cardinality_budgets_surface_integrity_failure(self) -> None:
        monitor = ObservabilityIntegrityMonitor(
            (
                TelemetrySourcePolicy(
                    "runtime",
                    max_loss_fraction=0.10,
                    cardinality_budget=1,
                ),
            )
        )
        monitor.observe(obs(1, delivered=False, series="a"))
        monitor.observe(obs(2, delivered=True, series="b"))
        source = monitor.report().sources[0]
        self.assertEqual(source.status, IntegrityStatus.BREACHED)
        self.assertIn("loss-budget-exceeded", source.reasons)
        self.assertIn("cardinality-budget-exceeded", source.reasons)

    def test_trace_completeness_has_deadline(self) -> None:
        monitor = ObservabilityIntegrityMonitor((TelemetrySourcePolicy("runtime"),))
        monitor.heartbeat("runtime")
        monitor.expect_trace(
            "trace-1",
            ("api", "orchestrator", "provider"),
            deadline_after_ticks=2,
        )
        monitor.observe_trace_stage("trace-1", "api")
        monitor.advance(2)
        report = monitor.report()
        self.assertEqual(report.status, IntegrityStatus.DEGRADED)
        self.assertEqual(report.incomplete_traces, ("trace-1",))

    def test_complete_trace_does_not_degrade(self) -> None:
        monitor = ObservabilityIntegrityMonitor((TelemetrySourcePolicy("runtime"),))
        monitor.heartbeat("runtime")
        monitor.expect_trace(
            "trace-1", ("api", "provider"), deadline_after_ticks=3
        )
        monitor.observe_trace_stage("trace-1", "api")
        monitor.observe_trace_stage("trace-1", "provider")
        monitor.advance(1)
        self.assertEqual(monitor.report().status, IntegrityStatus.HEALTHY)

    def test_resilient_sink_failure_imports_as_loss(self) -> None:
        def broken(_event):
            raise RuntimeError("sink down")

        telemetry = ResilientTelemetry(sink=broken)
        telemetry.emit(
            "critical.receipt",
            payload={"ok": True},
            labels={"plane": "control"},
            correlation_id="corr",
        )
        monitor = ObservabilityIntegrityMonitor(
            (TelemetrySourcePolicy("runtime", max_loss_fraction=0.0),)
        )
        monitor.audit_resilient_telemetry("runtime", telemetry)
        source = monitor.report().sources[0]
        self.assertEqual(source.lost, 1)
        self.assertEqual(source.status, IntegrityStatus.BREACHED)

    def test_report_is_non_authoritative(self) -> None:
        monitor = ObservabilityIntegrityMonitor((TelemetrySourcePolicy("runtime"),))
        data = monitor.report().as_dict()
        self.assertFalse(data["canonical_state_dependency"])
        self.assertFalse(data["completion_checkbox"])
        self.assertFalse(data["verification_signature"])

    def test_canonical_and_governed_ai_files_are_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            (root / "skeleton/observability/integrity.py").read_bytes(),
            (root / "skeleton/ai/runtime/observability/integrity.py").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
