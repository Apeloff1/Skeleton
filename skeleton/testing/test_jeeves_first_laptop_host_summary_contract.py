"""Read-only composed host observations are not physical device/release proof."""
from __future__ import annotations
import unittest

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.host_probes.cpu import CpuObservation
from skeleton.jeeves.native_fabric.laptop_ops.host_probes.memory import MemoryObservation
from skeleton.jeeves.native_fabric.laptop_ops.host_probes.disk import DiskObservation
from skeleton.jeeves.native_fabric.laptop_ops.host_probes.gguf_header import GGUFHeaderObservation
from skeleton.jeeves.native_fabric.laptop_ops.host_probes.summary import HostObservation

def good():
    return HostObservation(
        CpuObservation(4,16,8,8),
        MemoryObservation(8000000000,16000000000,10000000000,"posix_physical"),
        DiskObservation(1000000000,80000000000,30000000000,"posix_fstatvfs"),
        GGUFHeaderObservation("header_plausible",8000000000,3,True),
    )

class HostSummaryContractTests(unittest.TestCase):
    def test_all_four_observations_are_typed_and_diagnostic_only(self):
        observed=good()
        self.assertTrue(observed.structural_preconditions_observed)
        self.assertEqual(observed.observational_holds, ())
        record=observed.to_record()
        self.assertTrue(record["structural_preconditions_observed"])
        self.assertEqual(len(record["independent_qualification_holds"]),5)
        self.assertFalse(record["real_native_generation_witnessed"])
        self.assertFalse(record["native_model_started"])
        self.assertFalse(record["physical_device_qualified"])
        self.assertFalse(record["release_certified"])

    def test_bad_resource_cannot_leave_structural_preconditions_green(self):
        baseline=good()
        for corrupt in (
            HostObservation(CpuObservation(64,16,8,8),baseline.memory,baseline.storage,baseline.gguf),
            HostObservation(baseline.cpu,MemoryObservation(16000000000,16000000000,10000000000,"posix_physical"),baseline.storage,baseline.gguf),
            HostObservation(baseline.cpu,baseline.memory,DiskObservation(100000000000,80000000000,30000000000,"posix_fstatvfs"),baseline.gguf),
            HostObservation(baseline.cpu,baseline.memory,baseline.storage,GGUFHeaderObservation("wrong_magic",8,None,True)),
        ):
            with self.subTest(holds=corrupt.observational_holds):
                self.assertFalse(corrupt.structural_preconditions_observed)
                self.assertTrue(corrupt.observational_holds)
                self.assertFalse(corrupt.to_record()["release_certified"])

    def test_untyped_composition_is_never_accepted(self):
        base=good()
        with self.assertRaises(LaptopGateHold):
            HostObservation("ok",base.memory,base.storage,base.gguf)
        with self.assertRaises(LaptopGateHold):
            HostObservation(base.cpu,None,base.storage,base.gguf)
