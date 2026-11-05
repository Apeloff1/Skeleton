"""Native CPU admission counts must be strict and finite."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.host_probes.cpu import (
    CpuObservation, observe_cpu,
)

class CpuContractTests(unittest.TestCase):
    def test_bad_request_limits_rejected(self):
        for bad in (None,True,False,0,-1,65,1.5,"4",[],{}):
            with self.subTest(value=bad),self.assertRaises(LaptopGateHold):
                observe_cpu(bad)

    def test_bad_telemetry_rejected(self):
        for invalid in (True,0,-1,4097,1.2,"4",[],{}):
            with self.subTest(value=invalid),self.assertRaises(LaptopGateHold):
                CpuObservation(4,invalid,None,None)
            with self.subTest(value=invalid),self.assertRaises(LaptopGateHold):
                CpuObservation(4,None,invalid,None)
            with self.subTest(value=invalid),self.assertRaises(LaptopGateHold):
                CpuObservation(4,None,None,invalid)

    def test_affinity_overrules_logical_machine_size(self):
        snapshot=CpuObservation(8,64,None,2)
        self.assertEqual(snapshot.observed_ceiling,2)
        self.assertFalse(snapshot.request_fits_observed_limit)
        self.assertTrue(snapshot.process_quota_observed)

    def test_no_unqualified_trust_grant_appears_in_report(self):
        report=CpuObservation(1,8,8,None).to_record()
        self.assertTrue(report["request_fits_observed_limit"])
        self.assertFalse(report["model_started"])
        self.assertFalse(report["physical_device_qualified"])
        self.assertFalse(report["release_certified"])
