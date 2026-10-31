"""Real canonical resource monitor contracts with deterministic fake clock."""
from __future__ import annotations
import json
import pytest
from skeleton.ai.runtime.inference.adaptive_serving import ServingResources
from skeleton.ai.runtime.inference.resource_monitor import (
    ResourceMonitorError, main, monitor_resources,
)


def test_payload_free_monitor_receipts_are_deterministic() -> None:
    def sample() -> ServingResources:
        return ServingResources(memory_used_fraction=0.2, source="measured-test")
    def clock() -> float:
        return 1.0
    def sleep(_: float) -> None:
        pass
    first = list(monitor_resources(count=2, interval_seconds=0.0, operator_max=4, sample=sample, clock=clock, sleep=sleep))
    second = list(monitor_resources(count=2, interval_seconds=0.0, operator_max=4, sample=sample, clock=clock, sleep=sleep))
    assert first == second
    assert first[0]["resource"]["source"] == "measured-test"
    assert first[0]["hardware_qualification"] == "not_assessed"
    assert len(first[0]["digest"]) == 64
    assert "prompt" not in json.dumps(first)


def test_pressure_monitor_reduces_local_concurrency() -> None:
    sample = lambda: ServingResources(memory_used_fraction=0.98, source="test-pressure")
    receipts = list(monitor_resources(count=1, interval_seconds=0, operator_max=8, sample=sample, clock=lambda: 1.0))
    assert receipts[0]["pressure"]["level"] == "critical"
    assert receipts[0]["effective_concurrency"] == 4
    assert receipts[0]["background_limit"] == 0


def test_invalid_sampler_fails_closed() -> None:
    with pytest.raises(ResourceMonitorError, match="noncanonical"):
        list(monitor_resources(count=1, interval_seconds=0, operator_max=2, sample=lambda: None))


def test_invalid_clock_fails_closed() -> None:
    with pytest.raises(ResourceMonitorError, match="monotonic"):
        list(monitor_resources(count=1, interval_seconds=0, operator_max=2, clock=lambda: float("nan")))


@pytest.mark.parametrize("count,interval,workers", [
    (0, 1.0, 2), (1001, 1.0, 2), (1, -1.0, 2),
    (1, float("nan"), 2), (1, 1.0, 0), (1, 1.0, 65),
])
def test_unbounded_monitor_configuration_rejected(count: int, interval: float, workers: int) -> None:
    with pytest.raises(ResourceMonitorError):
        list(monitor_resources(count=count, interval_seconds=interval, operator_max=workers))


def test_monitor_sleep_only_between_samples() -> None:
    calls: list[float] = []
    receipts = list(monitor_resources(
        count=3, interval_seconds=0.25, operator_max=2,
        sample=lambda: ServingResources(memory_used_fraction=0.1),
        clock=lambda: 1.0, sleep=calls.append,
    ))
    assert len(receipts) == 3
    assert calls == [0.25, 0.25]


def test_cli_emits_one_canonical_json_receipt(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import skeleton.ai.runtime.inference.resource_monitor as monitor
    monkeypatch.setattr(monitor, "sample_serving_resources", lambda: ServingResources(memory_used_fraction=0.1))
    # The default sampler is bound at function definition time, so inject via
    # a small wrapper preserving the actual canonical monitor implementation.
    original = monitor.monitor_resources
    def patched(**kwargs):
        kwargs["sample"] = lambda: ServingResources(memory_used_fraction=0.1)
        return original(**kwargs)
    monkeypatch.setattr(monitor, "monitor_resources", patched)
    assert main(["--count", "1", "--operator-max", "2"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema"] == "skeleton.ai.local-resource-monitor.v1"
