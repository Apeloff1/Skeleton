from datetime import UTC, datetime

import pytest

from skeleton.frontier.telemetry import MetricSample, TelemetryBuffer


def test_telemetry_buffer_records_and_reads_latest():
    buffer = TelemetryBuffer()
    buffer.record(MetricSample("latency_ms", 10.0))
    buffer.record(MetricSample("latency_ms", 12.0))
    buffer.record(MetricSample("tokens", 4.0))
    assert buffer.values("latency_ms") == [10.0, 12.0]
    assert buffer.latest("latency_ms").value == 12.0


def test_metric_sample_requires_timezone_aware_timestamp():
    try:
        MetricSample("x", 1.0, datetime.now())
    except ValueError:
        pass
    else:
        raise AssertionError("naive timestamps must fail")

    assert MetricSample("x", 1.0, datetime.now(UTC)).name == "x"


def test_telemetry_evicts_old_samples_and_summarizes_retained_window():
    buffer = TelemetryBuffer(capacity=2)
    for value in [1, 10, 20]:
        buffer.record(MetricSample("latency", value))
    assert buffer.values("latency") == [10, 20]
    assert buffer.dropped == 1
    assert buffer.summary("latency")["p50"] == 15
    assert buffer.summary("latency")["p95"] == 19.5
    assert buffer.summary("missing")["count"] == 0


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "1"])
def test_telemetry_rejects_non_numeric_or_non_finite_values(value):
    with pytest.raises(ValueError):
        MetricSample("metric", value)


def test_telemetry_tags_are_detached_and_immutable():
    tags = {"agent": "npc"}
    sample = MetricSample("calls", 1, tags=tags)
    tags["agent"] = "other"
    assert sample.tags["agent"] == "npc"
    with pytest.raises(TypeError):
        sample.tags["agent"] = "mutated"
