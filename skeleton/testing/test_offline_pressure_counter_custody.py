"""Source-level pressure telemetry regressions; not hardware qualification."""
from __future__ import annotations

import sys

import pytest

from skeleton.app.offline_kernel_counters import MAX_KERNEL_COUNTER, read_kernel_ascii, uint_counter
from skeleton.app.offline_cpu_throttle import CPUThrottleController, CPUThrottleSample, probe_cpu_throttle
from skeleton.app.offline_swap_churn import SwapChurnController, SwapCounters, probe_swap_counters
from skeleton.app.offline_reclaim_pressure import ReclaimCounters, ReclaimPressureController, probe_reclaim_counters
from skeleton.app.offline_io_pressure import IOPressure, IOPressureController, probe_io_pressure

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux kernel-file fixture")


@pytest.mark.parametrize("value", ["01", "+1", "1_0", "9" * 5000, str(MAX_KERNEL_COUNTER + 1)])
def test_unsigned_kernel_counter_bounds(value):
    with pytest.raises(ValueError):
        uint_counter(value)


def test_counter_reader_refuses_oversize_and_symlink(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"x" * 4097)
    with pytest.raises(ValueError):
        read_kernel_ascii(source, maximum=4096)
    alias = tmp_path / "alias"
    alias.symlink_to(source)
    with pytest.raises(OSError):
        read_kernel_ascii(alias, maximum=4096)


def test_counter_reader_refuses_fifo_without_blocking(tmp_path):
    import os
    pipe = tmp_path / "fifo"
    os.mkfifo(pipe)
    with pytest.raises(ValueError):
        read_kernel_ascii(pipe, maximum=64)


def test_cpu_and_swap_probes_reject_oversized_and_duplicate_counters(tmp_path):
    cpu = tmp_path / "cpu.stat"
    cpu.write_text("nr_periods 100\nnr_throttled 20\nthrottled_usec 1\n")
    assert probe_cpu_throttle(tmp_path) == CPUThrottleSample(100, 20, 1)
    cpu.write_text("nr_periods " + "9" * 4097)
    assert probe_cpu_throttle(tmp_path) is None
    vm = tmp_path / "vmstat"
    vm.write_text("pswpin 1\npswpout 2\n")
    assert probe_swap_counters(vm) == SwapCounters(1, 2)
    vm.write_text("pswpin 1\npswpout 2\npswpout 3\n")
    assert probe_swap_counters(vm) is None


def test_cpu_telemetry_gap_preserves_hold_and_invalidates_rate():
    controller = CPUThrottleController()
    controller.observe(CPUThrottleSample(100, 0, 0))
    controller.observe(CPUThrottleSample(200, 50, 100))
    controller.observe(None)
    assert controller.snapshot()["backpressure"]
    assert controller.snapshot()["observed_throttled_ratio"] is None
    controller.observe(CPUThrottleSample(300, 50, 100))
    assert controller.snapshot()["backpressure"]
    controller.observe(CPUThrottleSample(400, 50, 100))
    assert not controller.snapshot()["backpressure"]


def test_swap_telemetry_gap_requires_new_measured_interval():
    clock = iter([0, 10**9, 2 * 10**9, 3 * 10**9, 4 * 10**9])
    controller = SwapChurnController(clock_ns=lambda: next(clock), page_size=4096)
    ram = 1024 * 1024
    for sample in (SwapCounters(0, 0), SwapCounters(100, 0), None, SwapCounters(100, 0)):
        controller.observe(sample, physical_ram_bytes=ram)
    assert controller.snapshot()["backpressure"]
    assert controller.snapshot()["observed_bytes_per_second"] is None
    controller.observe(SwapCounters(100, 0), physical_ram_bytes=ram)
    assert not controller.snapshot()["backpressure"]


def test_reclaim_gap_resets_consecutive_quiet_recovery():
    controller = ReclaimPressureController()
    def observe(sample, index):
        controller.observe(sample, physical_ram_bytes=1024 * 1024, now_ns=index * 10**9)
    initial = ReclaimCounters("cgroup_v2", 0, 0, 0)
    stressed = ReclaimCounters("cgroup_v2", 100, 0, 100)
    observe(initial, 0)
    for i in range(1, 4):
        observe(stressed, i)
    assert controller.snapshot()["quiet_intervals"] == 2
    assert controller.snapshot()["backpressure"]
    observe(None, 4)
    assert controller.snapshot()["quiet_intervals"] == 0
    for i in range(5, 8):
        observe(stressed, i)
    assert controller.snapshot()["backpressure"]
    observe(stressed, 8)
    assert not controller.snapshot()["backpressure"]


def test_malformed_cgroup_reclaim_cannot_fall_back_to_calm_host(tmp_path):
    cg = tmp_path / "memory.stat"
    host = tmp_path / "vmstat"
    cg.write_text("pgscan 1\npgscan 2\n")
    host.write_text("pgscan 1\npgsteal 1\npgmajfault 0\n")
    assert probe_reclaim_counters(cg, host) is None


def test_io_scope_switch_cannot_clear_hold_in_one_observation():
    controller = IOPressureController()
    controller.observe(IOPressure("cgroup", 25, 10, 100, 50))
    controller.observe(IOPressure("host", 0, 0, 200, 100))
    assert controller.snapshot()["congested"]
    controller.observe(IOPressure("host", 0, 0, 201, 100))
    assert not controller.snapshot()["congested"]


def test_io_rejects_inconsistent_psi_and_noncanonical_numbers(tmp_path):
    path = tmp_path / "io.pressure"
    path.write_text("some avg10=1.0 total=1\nfull avg10=2.0 total=2\n")
    assert probe_io_pressure(tmp_path) is None
    path.write_text("some avg10=0_0 total=1\nfull avg10=0.0 total=0\n")
    assert probe_io_pressure(tmp_path) is None
