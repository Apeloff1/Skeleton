"""Runtime pressure supervisor contracts after the desktop implementation.

All synthetic pressure observations are test-only. They cannot establish
actual GGUF/GPU pressure qualification. The production observer reads real
host RAM, cgroup memory, SQLite disk free and native child RSS before its
parent may continue unbounded model work.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import desktop_pressure as pressure
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capacity_plan import (
    CgroupObservation,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_client import (
    DesktopConfig, DesktopBridgeHold,
)


MIB = 1024 ** 2
GIB = 1024 ** 3


def host(*, memory=8 * GIB, disk=5 * GIB):
    return {
        "schema": "laptop-device-observation.v1",
        "memory_total_bytes": 16 * GIB,
        "memory_available_bytes": memory,
        "swap_free_bytes": 4 * GIB,
        "state_storage_available_bytes": disk,
        "measurement_only": True,
        "qualified_device": False,
    }


def cgroup(available=None):
    return CgroupObservation(
        available, None, available is not None, False, "cgroup-v2",
    )


def sample(*, critical=(), rss=2 * GIB):
    return pressure.PressureSample(
        observed_monotonic_ms=1000,
        host_available_bytes=8 * GIB,
        cgroup_available_bytes=4 * GIB,
        effective_available_bytes=4 * GIB,
        state_disk_available_bytes=5 * GIB,
        native_rss_bytes=rss, native_start_ticks=12345,
        pressure_reasons=tuple(critical),
    )


class PressurePolicyTests(unittest.TestCase):
    def test_boolean_or_unbounded_pressure_policy_is_denied(self):
        for values in (
            {"minimum_available_ram_bytes": True},
            {"minimum_available_ram_bytes": 0},
            {"minimum_state_disk_bytes": -1},
            {"maximum_native_rss_bytes": -1},
            {"sample_interval_ms": 20},
            {"sample_interval_ms": 5001},
            {"consecutive_critical_samples": 0},
            {"consecutive_critical_samples": 100},
            {"maximum_observation_errors": 4},
        ):
            with self.subTest(values=values), self.assertRaises(
                pressure.DesktopPressureHold,
            ):
                pressure.PressurePolicy(**values)

    def test_resource_guard_is_off_by_default_in_non_gui_api(self):
        config = DesktopConfig(
            model_root="/trusted/model", state_dir="/private/state",
            tenant="local", subject="owner",
        )
        self.assertFalse(config.enable_pressure_guard)

    def test_explicit_guard_limits_are_validated_before_native_activation(self):
        for values in (
            {"enable_pressure_guard": 1},
            {"enable_pressure_guard": "yes"},
            {"minimum_free_ram_bytes": 0},
            {"minimum_free_disk_bytes": False},
            {"pressure_interval_ms": -100},
        ):
            with self.subTest(values=values), self.assertRaises(
                (pressure.DesktopPressureHold, DesktopBridgeHold),
            ):
                DesktopConfig(
                    model_root="/trusted/model", state_dir="/private/state",
                    tenant="local", subject="owner",
                    **values,
                )

    def test_public_pressure_receipt_is_measurement_not_device_qualification(self):
        detail = sample(critical=("native-resident-ceiling",)).public_receipt()
        self.assertTrue(detail["measurement_only"])
        self.assertFalse(detail["device_qualified"])
        self.assertFalse(detail["release_certified"])
        self.assertEqual(detail["pressure_reasons"], ["native-resident-ceiling"])
        self.assertNotIn("private_model_path", detail)


class ProcessPressureObservationTests(unittest.TestCase):
    def _observe(self, *, available_ram=8*GIB, available_disk=4*GIB,
                 cgroup_ram=4*GIB, rss=2*GIB,
                 expected_ticks=12345, actual_ticks=12345):
        source = [
            actual_ticks,
            actual_ticks,
        ]
        with (
            mock.patch.object(
                pressure, "_process_start_ticks",
                side_effect=lambda _: source.pop(0),
            ),
            mock.patch.object(
                pressure, "inspect_device",
                return_value=host(memory=available_ram, disk=available_disk),
            ),
            mock.patch.object(
                pressure, "observe_cgroup",
                return_value=cgroup(cgroup_ram),
            ),
            mock.patch.object(
                pressure, "_resident_bytes",
                return_value=rss,
            ),
        ):
            return pressure.observe_pressure(
                pid=1234, original_start_ticks=expected_ticks,
                state_dir=Path("/private/state"),
                policy=pressure.PressurePolicy(
                    minimum_available_ram_bytes=512*MIB,
                    minimum_state_disk_bytes=256*MIB,
                    maximum_native_rss_bytes=6*GIB,
                ),
            )

    def test_healthy_cgroup_host_disk_and_native_rss(self):
        observed = self._observe()
        self.assertEqual(observed.effective_available_bytes, 4*GIB)
        self.assertEqual(observed.native_rss_bytes, 2*GIB)
        self.assertFalse(observed.critical)

    def test_real_effective_cgroup_memory_is_not_ignored(self):
        observed = self._observe(cgroup_ram=200*MIB)
        self.assertTrue(observed.critical)
        self.assertIn("cgroup-ram-floor", observed.pressure_reasons)

    def test_host_memory_floor_and_state_disk_floor_are_independent(self):
        observed = self._observe(
            available_ram=128*MIB, available_disk=100*MIB,
        )
        self.assertTrue(observed.critical)
        self.assertIn("host-ram-floor", observed.pressure_reasons)
        self.assertIn("state-disk-floor", observed.pressure_reasons)

    def test_native_worker_resident_memory_ceiling_is_enforced(self):
        observed = self._observe(rss=7*GIB)
        self.assertEqual(observed.pressure_reasons, ("native-resident-ceiling",))

    def test_reused_or_changed_pid_cannot_be_an_observation_of_our_worker(self):
        with self.assertRaises(pressure.DesktopPressureHold):
            self._observe(actual_ticks=9999)


class FakeNativeProcess:
    def __init__(self):
        self.pid = 1234
        self.alive = True
    def poll(self):
        return None if self.alive else 2


class DeferredThread:
    def __init__(self, *, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
    def start(self):
        self.started = True


class ParentPressureLifecycleTests(unittest.TestCase):
    def _supervisor(self, first, *, consecutive=2, errors=1):
        process = FakeNativeProcess()
        events = []
        policies = pressure.PressurePolicy(
            consecutive_critical_samples=consecutive,
            maximum_observation_errors=errors,
            sample_interval_ms=100,
        )
        observer = mock.Mock(return_value=first)
        with (
            mock.patch.object(pressure.subprocess, "Popen", FakeNativeProcess),
            mock.patch.object(pressure, "_process_start_ticks", return_value=12345),
        ):
            monitor = pressure.NativePressureSupervisor(
                process, state_dir=Path("/private/state"),
                policy=policies, revoke=lambda reason: events.append(reason),
                observation=observer,
            )
        return process, monitor, events, observer

    def test_initial_healthy_admission_and_bounded_monitor(self):
        proc, monitor, events, observer = self._supervisor(sample())
        with (
            mock.patch.object(pressure, "_process_start_ticks", return_value=12345),
            mock.patch.object(pressure.threading, "Thread", DeferredThread),
        ):
            actual = monitor.start()
        self.assertFalse(actual.critical)
        self.assertIsNone(monitor.reason)
        self.assertEqual(events, [])
        self.assertTrue(monitor._thread.started)
        self.assertFalse(monitor.latest["device_qualified"])
        monitor.stop()

    def test_first_critical_sample_prevents_admission(self):
        proc, monitor, events, observer = self._supervisor(
            sample(critical=("cgroup-ram-floor",)),
        )
        with mock.patch.object(
            pressure, "_process_start_ticks", return_value=12345,
        ):
            with self.assertRaises(pressure.DesktopPressureHold):
                monitor.start()
        self.assertEqual(events, ["cgroup-ram-floor"])
        self.assertEqual(monitor.reason, "cgroup-ram-floor")

    def test_sustained_pressure_revokes_once_with_no_native_retry(self):
        proc, monitor, events, observer = self._supervisor(sample())
        reason = "state-disk-floor"
        self.assertIsNone(monitor._admit(sample(critical=(reason,))))
        self.assertEqual(monitor._admit(sample(critical=(reason,))), reason)
        monitor._fatal(reason)
        monitor._fatal(reason)
        self.assertEqual(events, [reason])
        self.assertEqual(monitor.reason, reason)
        self.assertTrue(monitor._stop_event.is_set())

    def test_recovered_memory_resets_pressure_hysteresis(self):
        proc, monitor, events, observer = self._supervisor(sample())
        monitor._admit(sample(critical=("host-ram-floor",)))
        monitor._admit(sample())
        self.assertIsNone(
            monitor._admit(sample(critical=("host-ram-floor",))),
        )
        self.assertEqual(events, [])

    def test_unknown_kernel_telemetry_has_bounded_fail_closed_budget(self):
        proc, monitor, events, observer = self._supervisor(
            sample(), errors=0,
        )
        monitor._start_ticks = 12345
        observer.side_effect = pressure.DesktopPressureHold("telemetry unavailable")
        monitor._stop_event.wait = mock.Mock(side_effect=[False, True])
        monitor._monitor()
        self.assertEqual(events, ["telemetry-unavailable"])
        self.assertEqual(monitor.reason, "telemetry-unavailable")

    def test_terminated_native_child_is_not_revived_by_supervisor(self):
        proc, monitor, events, observer = self._supervisor(sample())
        monitor._start_ticks = 12345
        proc.alive = False
        monitor._stop_event.wait = mock.Mock(side_effect=[False, True])
        monitor._monitor()
        self.assertEqual(events, [])
        self.assertIsNone(monitor.reason)
        observer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
