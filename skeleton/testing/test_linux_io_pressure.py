"""Measured Linux IO PSI and backpressure regressions."""
from __future__ import annotations
import pytest
from skeleton.ai.runtime.inference.adaptive_serving import AdaptiveServingController, ServingResources
from skeleton.ai.runtime.inference.linux_io_pressure import read_linux_io_pressure

SAMPLE = "some avg10=42.00 avg60=2.00 avg300=1.25 total=123456\nfull avg10=11.00 avg60=1.00 avg300=0.50 total=1234\n"

def test_scoped_io_pressure_precedes_host() -> None:
    seen: list[str] = []
    def read(path: str) -> str:
        seen.append(path)
        return SAMPLE
    result = read_linux_io_pressure(read, cgroup_directory="/sys/fs/cgroup/work")
    assert seen == ["/sys/fs/cgroup/work/io.pressure"]
    assert result.some_avg10 == 0.42
    assert result.full_avg10 == 0.11
    assert result.source == "linux_cgroup_io_psi"

def test_missing_scoped_io_pressure_falls_back_to_host() -> None:
    def read(path: str) -> str:
        if path.endswith("io.pressure"):
            raise FileNotFoundError(path)
        return SAMPLE
    assert read_linux_io_pressure(read, cgroup_directory="/sys/fs/cgroup/work").source == "linux_host_io_psi"

def test_invalid_scoped_io_pressure_never_launders_host() -> None:
    seen: list[str] = []
    def read(path: str) -> str:
        seen.append(path)
        raise PermissionError(path)
    result = read_linux_io_pressure(read, cgroup_directory="/sys/fs/cgroup/work")
    assert result.some_avg10 is None
    assert result.source == "linux_io_psi_invalid"
    assert seen == ["/sys/fs/cgroup/work/io.pressure"]

def test_missing_kernel_interface_is_unknown() -> None:
    def read(path: str) -> str:
        raise FileNotFoundError(path)
    assert read_linux_io_pressure(read).some_avg10 is None

@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -0.01, 1.01])
def test_invalid_io_fraction_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        ServingResources(io_stall_fraction=value)

def test_io_stalls_throttle_concurrent_local_work() -> None:
    ctl = AdaptiveServingController(operator_max=8)
    ctl.update(ServingResources(io_stall_fraction=0.42, io_full_stall_fraction=0.11), now=1.0, queued=8)
    assert ctl.reason == "io_stall_pressure"
    assert ctl.level == "elevated"
    assert ctl.effective_concurrency == 7

def test_full_io_stall_is_critical_and_pauses_background() -> None:
    ctl = AdaptiveServingController(operator_max=8)
    ctl.update(ServingResources(io_full_stall_fraction=0.35), now=1.0, queued=8)
    assert ctl.reason == "io_stall_critical"
    assert ctl.effective_concurrency == 4
    assert ctl.background_limit == 0

def test_io_stall_hysteresis_prevents_early_recovery() -> None:
    ctl = AdaptiveServingController(operator_max=4)
    ctl.configure({"cooldown_seconds": 0.5, "recovery_samples": 2}, now=0.0)
    ctl.update(ServingResources(io_stall_fraction=0.4), now=1.0, queued=4)
    ctl.update(ServingResources(io_stall_fraction=0.2), now=2.0, queued=4)
    assert ctl.effective_concurrency == 3
    ctl.update(ServingResources(io_stall_fraction=0.0), now=3.0, queued=4)
    ctl.update(ServingResources(io_stall_fraction=0.0), now=4.0, queued=4)
    assert ctl.effective_concurrency == 4
