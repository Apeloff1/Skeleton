"""Real local CPU snapshot collection never executes native or probes private data."""
from __future__ import annotations
import unittest
from unittest import mock
from skeleton.jeeves.native_fabric.laptop_ops.host_probes import cpu

class CpuProbeTests(unittest.TestCase):
    def test_process_and_affinity_envelopes_are_all_conservative(self):
        with (
            mock.patch.object(cpu.os,"cpu_count",return_value=16),
            mock.patch.object(cpu.os,"process_cpu_count",create=True,return_value=8),
            mock.patch.object(cpu.os,"sched_getaffinity",create=True,return_value=set(range(4))),
        ):
            snapshot = cpu.observe_cpu(4)
            over = cpu.observe_cpu(5)
        self.assertEqual(snapshot.logical_cores,16)
        self.assertEqual(snapshot.process_cores,8)
        self.assertEqual(snapshot.affinity_cores,4)
        self.assertEqual(snapshot.observed_ceiling,4)
        self.assertTrue(snapshot.request_fits_observed_limit)
        self.assertFalse(over.request_fits_observed_limit)
        self.assertFalse(snapshot.to_record()["actual_cgroup_cpu_quota_verified"])
        self.assertFalse(snapshot.to_record()["model_started"])

    def test_missing_process_quota_is_not_treated_as_verified(self):
        with (
            mock.patch.object(cpu.os,"cpu_count",return_value=32),
            mock.patch.object(cpu.os,"process_cpu_count",None,create=True),
            mock.patch.object(cpu.os,"sched_getaffinity",None,create=True),
        ):
            report = cpu.observe_cpu(2)
        self.assertEqual(report.observed_ceiling,32)
        self.assertFalse(report.process_quota_observed)
        self.assertFalse(report.request_fits_observed_limit)

    def test_os_probe_exceptions_are_holds_not_trusted_values(self):
        with (
            mock.patch.object(cpu.os,"cpu_count",side_effect=OSError("restricted")),
            mock.patch.object(cpu.os,"process_cpu_count",create=True,side_effect=OSError("restricted")),
            mock.patch.object(cpu.os,"sched_getaffinity",create=True,side_effect=OSError("restricted")),
        ):
            observed=cpu.observe_cpu(1)
        self.assertIsNone(observed.observed_ceiling)
        self.assertFalse(observed.request_fits_observed_limit)
        self.assertFalse(observed.to_record()["release_certified"])

    def test_boolean_platform_count_does_not_coerce(self):
        with (
            mock.patch.object(cpu.os,"cpu_count",return_value=True),
            mock.patch.object(cpu.os,"process_cpu_count",create=True,return_value=0),
            mock.patch.object(cpu.os,"sched_getaffinity",create=True,return_value=set()),
        ):
            record=cpu.observe_cpu(1)
        self.assertIsNone(record.observed_ceiling)
        self.assertFalse(record.request_fits_observed_limit)
