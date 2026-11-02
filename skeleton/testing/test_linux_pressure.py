"""Linux PSI and local adaptive serving admission regressions."""
from __future__ import annotations
import pytest
from skeleton.ai.runtime.inference.adaptive_serving import AdaptiveServingController, ServingResources
from skeleton.ai.runtime.inference.linux_pressure import (
    PressureTelemetryError, parse_linux_memory_psi, read_linux_memory_pressure,
)
SAMPLE = "some avg10=12.50 avg60=2.00 avg300=1.25 total=123456\nfull avg10=4.00 avg60=1.00 avg300=0.50 total=1234\n"

def test_parse_measured_partial_and_full_stalls() -> None:
    assert parse_linux_memory_psi(SAMPLE) == (0.125, 0.04)
    assert parse_linux_memory_psi(SAMPLE.splitlines()[0]) == (0.125, None)

@pytest.mark.parametrize("raw", [
    "", "full avg10=1 avg60=0 avg300=0 total=1",
    "some avg10=nan avg60=0 avg300=0 total=1",
    "some avg10=101 avg60=0 avg300=0 total=1",
    "some avg10=-1 avg60=0 avg300=0 total=1",
    "some avg10=1 avg60=0 avg300=0 total=-1",
    "some avg10=1 avg60=0 avg300=0 total=1\nsome avg10=1 avg60=0 avg300=0 total=2",
    "some avg10=1 avg60=0 avg300=0 total=18446744073709551616",
])
def test_malformed_psi_never_becomes_healthy(raw: str) -> None:
    with pytest.raises(PressureTelemetryError):
        parse_linux_memory_psi(raw)

def test_cgroup_precedes_host() -> None:
    calls: list[str] = []
    def read(path: str) -> str:
        calls.append(path)
        return SAMPLE
    result = read_linux_memory_pressure(read, cgroup_directory="/sys/fs/cgroup/job")
    assert calls == ["/sys/fs/cgroup/job/memory.pressure"]
    assert result.source == "linux_cgroup_psi"

def test_missing_cgroup_falls_back_to_measured_host() -> None:
    def read(path: str) -> str:
        if path.endswith("memory.pressure"):
            raise FileNotFoundError(path)
        return SAMPLE
    assert read_linux_memory_pressure(read, cgroup_directory="/sys/fs/cgroup/job").source == "linux_host_psi"

def test_denied_cgroup_does_not_launder_host() -> None:
    def read(path: str) -> str:
        raise PermissionError(path)
    result = read_linux_memory_pressure(read, cgroup_directory="/sys/fs/cgroup/job")
    assert result.source == "linux_psi_invalid"
    assert result.some_avg10 is None

def test_unsupported_psi_remains_unknown() -> None:
    def read(path: str) -> str:
        raise FileNotFoundError(path)
    assert read_linux_memory_pressure(read).some_avg10 is None

@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -0.01, 1.01])
def test_reject_untrusted_pressure_measurement(value: object) -> None:
    with pytest.raises(ValueError):
        ServingResources(memory_stall_fraction=value)

def test_stall_pressure_throttles_and_recovers_hysteretically() -> None:
    ctl = AdaptiveServingController(operator_max=4)
    ctl.configure({"cooldown_seconds": 0.5, "recovery_samples": 2}, now=0.0)
    ctl.update(ServingResources(memory_stall_fraction=0.25), now=1.0, queued=4)
    assert (ctl.level, ctl.reason, ctl.effective_concurrency) == ("elevated", "memory_stall_pressure", 3)
    ctl.update(ServingResources(memory_stall_fraction=0.10), now=2.0, queued=4)
    assert ctl.effective_concurrency == 3
    ctl.update(ServingResources(memory_stall_fraction=0.0), now=3.0, queued=4)
    ctl.update(ServingResources(memory_stall_fraction=0.0), now=4.0, queued=4)
    assert ctl.effective_concurrency == 4

def test_full_stall_is_critical_even_when_free_memory_is_high() -> None:
    ctl = AdaptiveServingController(operator_max=8)
    ctl.update(ServingResources(memory_used_fraction=0.2, memory_full_stall_fraction=0.12), now=1.0, queued=8)
    assert ctl.reason == "memory_stall_critical"
    assert ctl.effective_concurrency == 4
    assert ctl.background_limit == 0
