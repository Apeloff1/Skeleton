"""Strict finite native RAM reservation and Windows memory-structure layout."""
from __future__ import annotations
import ctypes
import unittest
from unittest import mock
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.host_probes import memory

class MemoryContractTests(unittest.TestCase):
    def test_boolean_float_negative_and_unbounded_requests_are_refused(self):
        bad = (None,False,True,-1,0,1.1,"100",1<<41,[],{})
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(LaptopGateHold):
                    memory.observe_ram(value)

    def test_corrupt_records_and_partial_counters_refused(self):
        cases = (
            (2,None,2,"unknown"),
            (2,2,None,"unknown"),
            (2,0,0,"posix_physical"),
            (2,8,9,"posix_physical"),
            (2,True,1,"posix_physical"),
            (2,8,4,"unknown"),
            (2,8,4,"fake_sensor"),
        )
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(LaptopGateHold):
                    memory.MemoryObservation(*args)

    def test_read_only_windows_physical_structure_is_bounded(self):
        fields = dict(memory._MemoryStatusEx._fields_)
        self.assertEqual(fields["dwLength"],ctypes.c_ulong)
        self.assertEqual(fields["ullTotalPhys"],ctypes.c_ulonglong)
        self.assertEqual(fields["ullAvailPhys"],ctypes.c_ulonglong)
        self.assertGreaterEqual(ctypes.sizeof(memory._MemoryStatusEx),64)

    def test_posix_failure_uses_held_observation(self):
        with mock.patch.object(memory.os,"sysconf",side_effect=OSError("quota unavailable")):
            self.assertIsNone(memory._posix_physical())

    def test_physical_memory_fit_does_not_remove_separate_holds(self):
        report = memory.MemoryObservation(1024,8192,4096,"posix_physical").to_record()
        self.assertTrue(report["fits_observed_ram"])
        self.assertFalse(report["gpu_allocation_verified"])
        self.assertFalse(report["cgroup_or_wsl2_limit_verified"])
        self.assertFalse(report["physical_device_qualified"])
        self.assertFalse(report["release_certified"])
