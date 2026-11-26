"""Resource admission may narrow but never expand the canonical lease pool."""
from __future__ import annotations

from pathlib import Path
import unittest

from core.dragon_resource_governor import (
    PressureSample, ResourceGovernor, desired_capacity, sample_pressure,
    RESERVE_BYTES, SLICE_BYTES,
)

MIB = 1024 * 1024


class CapacityTests(unittest.TestCase):
    def test_memory_cpu_and_pressure_intersection(self):
        headroom = RESERVE_BYTES + SLICE_BYTES * 2
        sample = PressureSample(headroom, 4., .01, .1, 10.)
        self.assertEqual(desired_capacity(sample, ceiling=4, now=10.)[0], 2)
        self.assertEqual(desired_capacity(
            PressureSample(headroom, 4., .25, .1, 10.), ceiling=4, now=10.)[0], 0)
        self.assertEqual(desired_capacity(
            PressureSample(headroom, .5, .01, .1, 10.), ceiling=4, now=10.)[0], 1)
        self.assertEqual(desired_capacity(sample, ceiling=4, now=13.)[0], 0)
        self.assertEqual(desired_capacity(
            PressureSample(None, None, None, None, 10.), ceiling=4, now=10.)[0], 1)

    def test_throttles_immediately_recovers_one_step_per_stability_window(self):
        controller = ResourceGovernor(4)

        def healthy(at):
            return PressureSample(RESERVE_BYTES + SLICE_BYTES * 8, 8., 0., 0., at)

        self.assertEqual(controller.observe(healthy(0), now=0).limit, 1)
        self.assertEqual(controller.observe(healthy(3), now=3).limit, 2)
        self.assertEqual(controller.observe(healthy(6), now=6).limit, 3)
        self.assertEqual(controller.observe(healthy(9), now=9).limit, 4)
        bad = PressureSample(128 * MIB, 8., .30, 0., 10.)
        self.assertEqual(controller.observe(bad, now=10).limit, 0)
        self.assertEqual(controller.observe(healthy(11), now=11).limit, 0)
        self.assertEqual(controller.observe(healthy(14), now=14).limit, 1)
        self.assertFalse(controller.projection()["network_authority_expanded"])

    def test_tightest_cgroup_and_ancestor_not_host_memory(self):
        root = "/sys/fs/cgroup"
        files = {
            "/proc/self/cgroup": "0::/group/child\n",
            "/proc/meminfo": "MemAvailable: 16000000 kB\n",
            root + "/memory.max": str(8 * 1024 * MIB),
            root + "/memory.current": str(2 * 1024 * MIB),
            root + "/group/memory.max": str(2 * 1024 * MIB),
            root + "/group/memory.current": str(768 * MIB),
            root + "/group/child/memory.max": "max",
            root + "/group/child/memory.current": str(256 * MIB),
            root + "/group/cpu.max": "200000 100000",
            root + "/group/child/memory.pressure": "some avg10=12.00 avg60=0.00 avg300=0.00 total=1\n",
        }
        sample = sample_pressure(reader=lambda path: files.get(str(path), ""),
                                 clock=lambda: 5.)
        self.assertEqual(sample.available_bytes, 1280 * MIB)
        self.assertLessEqual(sample.cpu_cores, 2)
        self.assertEqual(sample.memory_pressure, .12)
        self.assertEqual(desired_capacity(sample, ceiling=4, now=5.)[0], 1)


if __name__ == "__main__":
    unittest.main()
