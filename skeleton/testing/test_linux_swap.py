"""Host/cgroup swap telemetry and fail-closed adaptive recovery tests."""
from __future__ import annotations
import pytest
from skeleton.ai.runtime.inference.adaptive_serving import AdaptiveServingController, ServingResources
from skeleton.ai.runtime.inference.linux_swap import read_linux_swap

HOST = "MemTotal: 12345 kB\nSwapTotal: 2048 kB\nSwapFree: 512 kB\n"

def test_measured_host_swap_fraction_and_bytes() -> None:
    state = read_linux_swap(lambda _: HOST)
    assert state.source == "linux_host_swap"
    assert state.used_fraction == 0.75
    assert state.available_bytes == 512 * 1024

def test_finite_cgroup_swap_precedes_host() -> None:
    seen: list[str] = []
    def read(path: str) -> str:
        seen.append(path)
        if path.endswith("memory.swap.max"):
            return "4096"
        if path.endswith("memory.swap.current"):
            return "1024"
        raise AssertionError("host swap should not be read")
    state = read_linux_swap(read, cgroup_directory="/sys/fs/cgroup/work")
    assert state.source == "linux_cgroup_swap"
    assert state.used_fraction == 0.25
    assert state.available_bytes == 3072
    assert len(seen) == 2

def test_unlimited_cgroup_uses_measured_host() -> None:
    def read(path: str) -> str:
        return "max" if path.endswith("memory.swap.max") else HOST
    assert read_linux_swap(read, cgroup_directory="/sys/fs/cgroup/work").source == "linux_host_swap"

def test_invalid_cgroup_swap_cannot_launder_host() -> None:
    def read(path: str) -> str:
        return "broken" if path.endswith("memory.swap.max") else HOST
    state = read_linux_swap(read, cgroup_directory="/sys/fs/cgroup/work")
    assert state.source == "linux_swap_invalid"
    assert state.used_fraction is None

@pytest.mark.parametrize("raw", [
    "SwapTotal: 100 kB\nSwapFree: 101 kB",
    "SwapTotal: NaN kB\nSwapFree: 1 kB",
    "SwapTotal: 100 kB\nSwapFree: -1 kB",
    "SwapTotal: 100 kB\nSwapTotal: 100 kB\nSwapFree: 1 kB",
])
def test_malformed_swap_metadata_fails_closed(raw: str) -> None:
    state = read_linux_swap(lambda _: raw)
    assert state.source == "linux_swap_invalid"

def test_swap_disabled_is_unknown_not_zero() -> None:
    state = read_linux_swap(lambda _: "SwapTotal: 0 kB\nSwapFree: 0 kB")
    assert state.used_fraction is None

@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -0.1, 1.1])
def test_reject_invalid_swap_fraction(value: object) -> None:
    with pytest.raises(ValueError):
        ServingResources(swap_used_fraction=value)

def test_unknown_telemetry_cannot_claim_healthy_recovery() -> None:
    ctl = AdaptiveServingController(operator_max=4)
    ctl.configure({"cooldown_seconds": 0.5, "recovery_samples": 2}, now=0.0)
    ctl.update(ServingResources(memory_used_fraction=0.98), now=1.0, queued=4)
    reduced = ctl.effective_concurrency
    for second in range(2, 8):
        ctl.update(ServingResources(), now=float(second), queued=4)
    assert ctl.effective_concurrency == reduced
    ctl.update(ServingResources(memory_used_fraction=0.2), now=8.0, queued=4)
    ctl.update(ServingResources(memory_used_fraction=0.2), now=9.0, queued=4)
    assert ctl.effective_concurrency > reduced

@pytest.mark.parametrize("elapsed,wait", [
    (float("nan"), 0.0), (float("inf"), 0.0), (-1.0, 0.0),
    (0.0, float("nan")), (0.0, float("inf")), (0.0, -1.0),
])
def test_invalid_latency_samples_never_poison_controller(elapsed: float, wait: float) -> None:
    ctl = AdaptiveServingController(operator_max=2)
    with pytest.raises(ValueError):
        ctl.observe(elapsed_ms=elapsed, queue_wait_ms=wait, failed=False)
    assert ctl.observations == 0
