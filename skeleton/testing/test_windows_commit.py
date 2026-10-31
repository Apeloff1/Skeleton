"""Windows commit probe: simulated ABI and pure page arithmetic."""
from __future__ import annotations
import ctypes
import pytest
from skeleton.ai.runtime.inference.adaptive_serving import AdaptiveServingController, ServingResources
from skeleton.ai.runtime.inference.windows_commit import (
    WindowsCommitError, _PerformanceInformation, _probe_psapi,
    interpret_windows_commit, probe_windows_commit,
)


def test_page_arithmetic_preserves_commit_headroom() -> None:
    state = interpret_windows_commit(75, 100, 4096)
    assert state.used_fraction == 0.75
    assert state.available_bytes == 25 * 4096
    assert state.source == "windows_commit"


@pytest.mark.parametrize("committed,limit,page", [
    (-1, 100, 4096), (101, 100, 4096), (1, 0, 4096),
    (1, 100, 0), (1, 100, 1 << 21), (1, 1 << 62, 4096),
])
def test_invalid_commit_counters_rejected(committed: int, limit: int, page: int) -> None:
    with pytest.raises(WindowsCommitError):
        interpret_windows_commit(committed, limit, page)


def test_simulated_windows_psapi_abi() -> None:
    class Function:
        argtypes = None
        restype = None
        def __call__(self, ptr, size):
            info = ctypes.cast(ptr, ctypes.POINTER(_PerformanceInformation))[0]
            assert size == ctypes.sizeof(_PerformanceInformation)
            info.CommitTotal = 75
            info.CommitLimit = 100
            info.PageSize = 4096
            return 1
    class Simulated:
        GetPerformanceInfo = Function()
    state = _probe_psapi(Simulated())
    assert state.available_bytes == 25 * 4096


def test_platform_gated_probe_does_not_fabricate_commit() -> None:
    result = probe_windows_commit()
    assert result.source in {"windows_commit", "windows_commit_unavailable"}
    if result.source == "windows_commit_unavailable":
        assert result.used_fraction is None


def test_high_commit_pressure_reduces_local_concurrency() -> None:
    ctl = AdaptiveServingController(operator_max=8)
    ctl.update(ServingResources(commit_used_fraction=0.94), now=1.0, queued=8)
    assert ctl.reason == "windows_commit_pressure"
    assert ctl.effective_concurrency == 7


def test_critical_commit_pressure_pauses_background() -> None:
    ctl = AdaptiveServingController(operator_max=8)
    ctl.update(ServingResources(commit_used_fraction=0.98), now=1.0, queued=8)
    assert ctl.reason == "windows_commit_critical"
    assert ctl.effective_concurrency == 4
    assert ctl.background_limit == 0


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_commit_fraction_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        ServingResources(commit_used_fraction=value)
