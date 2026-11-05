"""Absolute paths, strict reservation, conservative unknown filesystem cases."""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.host_probes import disk

class DiskContractTests(unittest.TestCase):
    def test_noncanonical_private_path_never_probed(self):
        for candidate in (None,"/tmp",Path("relative"),Path("/tmp/../home"),True):
            with self.subTest(candidate=str(candidate)),self.assertRaises(LaptopGateHold):
                disk.observe_disk(candidate,1)

    def test_boolean_negative_unbounded_or_string_reservations_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            for value in (None,True,False,0,-1,1.5,"100",1<<41):
                with self.subTest(value=value),self.assertRaises(LaptopGateHold):
                    disk.observe_disk(path,value)

    def test_bad_observation_counts_not_counted_as_headroom(self):
        for total,free in ((True,2),(10,True),(10,-1),(2,10),(0,0),(1<<64,100)):
            with self.subTest(total=total,free=free):
                with self.assertRaises(LaptopGateHold):
                    disk.DiskObservation(1,total,free,"posix_fstatvfs")

    def test_unknown_counter_pair_is_never_positive(self):
        unknown=disk.DiskObservation(1,None,None,"unknown")
        self.assertFalse(unknown.fits_observed_space)
        self.assertFalse(unknown.to_record()["physical_device_qualified"])
        self.assertFalse(unknown.to_record()["release_certified"])

    def test_corrupt_os_return_becomes_unknown_held_result(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)  # Preserve original platform semantics.
            with (
                mock.patch.object(disk.os,"name","posix"),
                mock.patch.object(disk,"_posix_disk",return_value=(True,1)),
            ):
                result=disk.observe_disk(path,1)
        self.assertEqual(result.source,"unknown")
        self.assertFalse(result.fits_observed_space)
