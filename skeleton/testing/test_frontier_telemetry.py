from datetime import datetime, timezone

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

    assert MetricSample("x", 1.0, datetime.now(timezone.utc)).name == "x"
