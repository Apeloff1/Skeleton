from __future__ import annotations

import shutil
import statistics
import subprocess
from collections import deque
from pathlib import Path

import pytest

from skeleton.observability.anomaly import AnomalyDetector as CanonicalAnomalyDetector
from skeleton.observability.jvm_accelerator import (
    AnomalyScanRow,
    HistogramSummary,
    JvmAcceleratorConfig,
    JvmObservabilityAccelerator,
)
from skeleton.observability.metrics import (
    AnomalyDetector as LegacyAnomalyDetector,
    MetricsCollector,
)


class _FakeAccelerator:
    minimum_batch_values = 1

    def __init__(self) -> None:
        self.summary_calls = 0
        self.scan_calls = 0

    def summarize_many(self, series: list[list[float]]) -> list[HistogramSummary]:
        self.summary_calls += 1
        return [self._summary(values) for values in series]

    def scan_anomalies(
        self,
        history: list[float],
        incoming: list[float],
        *,
        window_size: int,
        threshold: float,
        include_current: bool = False,
    ) -> list[AnomalyScanRow]:
        self.scan_calls += 1
        window: deque[float] = deque(history, maxlen=window_size)
        rows: list[AnomalyScanRow] = []
        for value in incoming:
            if include_current:
                window.append(value)
            ready = len(window) >= 10
            mean = statistics.mean(window) if ready else 0.0
            stdev = statistics.stdev(window) if ready and len(window) > 1 else 0.0
            anomalous = ready and stdev > 0 and abs(value - mean) > threshold * stdev
            rows.append(
                AnomalyScanRow(
                    ready=ready,
                    anomalous=anomalous,
                    mean=mean,
                    stdev=stdev,
                )
            )
            if not include_current:
                window.append(value)
        return rows

    @staticmethod
    def _summary(values: list[float]) -> HistogramSummary:
        ordered = sorted(values)
        p99 = ordered[int(len(ordered) * 0.99)] if len(ordered) > 1 else ordered[0]
        if len(ordered) % 2:
            p50 = ordered[len(ordered) // 2]
        else:
            middle = len(ordered) // 2
            p50 = (ordered[middle - 1] + ordered[middle]) / 2
        variance = statistics.variance(values) if len(values) > 1 else 0.0
        return HistogramSummary(
            count=len(values),
            minimum=min(values),
            maximum=max(values),
            mean=statistics.mean(values),
            sample_variance=variance,
            sample_stdev=variance ** 0.5,
            p50=p50,
            p90=ordered[min(len(ordered) - 1, int(len(ordered) * 0.90))],
            p95=ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
            p99=p99,
            total=sum(values),
        )


class _FailingAccelerator:
    minimum_batch_values = 1

    def summarize_many(self, series: list[list[float]]) -> list[HistogramSummary]:
        raise RuntimeError("simulated Java failure")

    def scan_anomalies(self, *args: object, **kwargs: object) -> list[AnomalyScanRow]:
        raise RuntimeError("simulated Java failure")


def _populate_metrics(collector: MetricsCollector) -> None:
    collector.increment("requests", 4)
    collector.gauge("workers", 3)
    for value in range(1, 101):
        collector.histogram("latency_ms", float(value), {"route": "reason"})
    for value in range(20):
        collector.histogram("queue_depth", float(value % 7))


def test_metrics_accelerated_snapshot_preserves_existing_shape_and_values() -> None:
    expected = MetricsCollector()
    accelerated = MetricsCollector(
        use_jvm_acceleration=True,
        accelerator=_FakeAccelerator(),
    )
    _populate_metrics(expected)
    _populate_metrics(accelerated)

    assert accelerated.snapshot() == expected.snapshot()
    stats = accelerated.acceleration_stats()
    assert stats["enabled"] is True
    assert stats["attempts"] == 1
    assert stats["successes"] == 1
    assert stats["fallbacks"] == 0


def test_metrics_accelerator_failure_falls_back_to_python_snapshot() -> None:
    expected = MetricsCollector()
    accelerated = MetricsCollector(
        use_jvm_acceleration=True,
        accelerator=_FailingAccelerator(),
    )
    _populate_metrics(expected)
    _populate_metrics(accelerated)

    assert accelerated.snapshot() == expected.snapshot()
    assert accelerated.acceleration_stats()["fallbacks"] == 1


def test_metrics_small_batches_do_not_pay_accelerator_overhead() -> None:
    fake = _FakeAccelerator()
    fake.minimum_batch_values = 10_000
    collector = MetricsCollector(use_jvm_acceleration=True, accelerator=fake)
    _populate_metrics(collector)

    result = collector.snapshot()

    assert result["histograms"]
    assert fake.summary_calls == 0
    assert collector.acceleration_stats()["bypassed_small_batch"] == 1


def _report_signature(report: object) -> object:
    if report is None:
        return None
    return (
        report.metric_name,
        report.observed_value,
        report.expected_range[0],
        report.expected_range[1],
        report.severity,
        report.context,
    )


def test_canonical_statistical_batch_matches_sequential_detector() -> None:
    baseline = CanonicalAnomalyDetector(window_size=32, strategy="statistical")
    accelerated = CanonicalAnomalyDetector(
        window_size=32,
        strategy="statistical",
        use_jvm_acceleration=True,
        accelerator=_FakeAccelerator(),
    )
    values = [
        10.0 + (index % 5) * 0.25
        for index in range(80)
    ]
    values[33] = 40.0
    values[61] = -20.0

    expected = [
        baseline.observe(value, metric_name="latency", context={"route": "jeeves"})
        for value in values
    ]
    actual = accelerated.observe_many(
        values,
        metric_name="latency",
        context={"route": "jeeves"},
    )

    assert [_report_signature(item) for item in actual] == [
        _report_signature(item) for item in expected
    ]
    assert accelerated.stats() == baseline.stats()
    assert accelerated.acceleration_stats()["successes"] == 1


def test_canonical_stateful_strategies_stay_on_python_path() -> None:
    fake = _FakeAccelerator()
    detector = CanonicalAnomalyDetector(
        strategy="adaptive",
        use_jvm_acceleration=True,
        accelerator=fake,
    )

    detector.observe_many([float(index) for index in range(20)])

    assert fake.scan_calls == 0
    assert detector.acceleration_stats()["attempts"] == 0


def test_legacy_batch_semantics_match_sequential_detector() -> None:
    baseline = LegacyAnomalyDetector(window_size=24)
    accelerated = LegacyAnomalyDetector(
        window_size=24,
        use_jvm_acceleration=True,
        accelerator=_FakeAccelerator(),
    )
    values = [5.0 + (index % 4) for index in range(50)]
    values[30] = 100.0

    expected = [baseline.observe(value) for value in values]
    actual = accelerated.observe_many(values)

    assert actual == expected
    assert accelerated.stats() == baseline.stats()
    assert accelerated.acceleration_stats()["successes"] == 1


def test_batch_accelerator_failure_preserves_python_detector_behavior() -> None:
    baseline = CanonicalAnomalyDetector(window_size=20, strategy="statistical")
    accelerated = CanonicalAnomalyDetector(
        window_size=20,
        strategy="statistical",
        use_jvm_acceleration=True,
        accelerator=_FailingAccelerator(),
    )
    values = [float(index % 8) for index in range(30)] + [100.0]

    expected = [baseline.observe(value) for value in values]
    actual = accelerated.observe_many(values)

    assert [_report_signature(item) for item in actual] == [
        _report_signature(item) for item in expected
    ]
    assert accelerated.stats() == baseline.stats()
    assert accelerated.acceleration_stats()["fallbacks"] == 1


def _java_major(java: str) -> int | None:
    completed = subprocess.run(
        [java, "-version"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    first = (completed.stderr or completed.stdout).splitlines()
    if not first:
        return None
    line = first[0]
    marker = 'version "'
    if marker not in line:
        return None
    version = line.split(marker, 1)[1].split('"', 1)[0]
    head = version.split(".", 1)[0]
    if head == "1" and "." in version:
        head = version.split(".", 2)[1]
    try:
        return int(head)
    except ValueError:
        return None


def _real_config() -> JvmAcceleratorConfig:
    java = shutil.which("java")
    if not java:
        pytest.skip("java is not installed")
    major = _java_major(java)
    if major is None or major < 21:
        pytest.skip("Java 21+ is required for virtual-thread accelerator tests")
    source = (
        Path(__file__).resolve().parents[2]
        / "java-accelerators"
        / "observability"
        / "AcceleratorMain.java"
    )
    return JvmAcceleratorConfig(
        java_binary=java,
        source=source,
        response_timeout_seconds=20,
        minimum_batch_values=1,
    )


def test_real_java_accelerator_roundtrip_and_numerical_contract() -> None:
    with JvmObservabilityAccelerator(_real_config()) as accelerator:
        assert accelerator.ping() >= 1

        summary = accelerator.summarize([float(i) for i in range(1, 101)])
        assert summary.count == 100
        assert summary.minimum == 1.0
        assert summary.maximum == 100.0
        assert summary.mean == pytest.approx(50.5)
        assert summary.p50 == pytest.approx(50.5)
        assert summary.p99 == 100.0

        many = accelerator.summarize_many([
            [1.0, 2.0, 3.0],
            [10.0, 20.0, 30.0, 40.0],
        ])
        assert [item.mean for item in many] == pytest.approx([2.0, 25.0])


def test_real_java_accelerator_supports_both_anomaly_window_contracts() -> None:
    history = [10.0 + (index % 3) for index in range(20)]
    incoming = [11.0, 10.0, 100.0]

    with JvmObservabilityAccelerator(_real_config()) as accelerator:
        exclude_current = accelerator.scan_anomalies(
            history,
            incoming,
            window_size=20,
            threshold=3.0,
            include_current=False,
        )
        include_current = accelerator.scan_anomalies(
            history,
            incoming,
            window_size=20,
            threshold=3.0,
            include_current=True,
        )

    assert len(exclude_current) == len(incoming)
    assert len(include_current) == len(incoming)
    assert exclude_current[-1].anomalous is True
    assert include_current[-1].anomalous is True
    assert exclude_current[-1].mean != include_current[-1].mean
