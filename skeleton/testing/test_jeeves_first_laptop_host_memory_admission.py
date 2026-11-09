"""Physical RAM observations are advisory and never native model grants."""
from __future__ import annotations
import unittest
from unittest import mock

from skeleton.jeeves.native_fabric.laptop_ops.host_probes import memory

class MemoryAdmissionTests(unittest.TestCase):
    def test_posix_page_accounting_and_reservation(self):
        pages = {"SC_PHYS_PAGES":2048,"SC_AVPHYS_PAGES":1024,"SC_PAGE_SIZE":4096}
        with (
            mock.patch.object(memory.os,"name","posix"),
            mock.patch.object(memory.os,"sysconf",side_effect=lambda key:pages[key]),
        ):
            fits = memory.observe_ram(2 * 1024 * 1024)
            exceeds = memory.observe_ram(8 * 1024 * 1024)
        self.assertEqual(fits.total_bytes,8 * 1024 * 1024)
        self.assertEqual(fits.available_bytes,4 * 1024 * 1024)
        self.assertTrue(fits.fits_observed_ram)
        self.assertFalse(exceeds.fits_observed_ram)
        self.assertFalse(fits.to_record()["cgroup_or_wsl2_limit_verified"])
        self.assertFalse(fits.to_record()["release_certified"])

    def test_unknown_os_counters_do_not_approve_allocation(self):
        with (
            mock.patch.object(memory.os,"name","posix"),
            mock.patch.object(memory,"_posix_physical",return_value=None),
        ):
            value = memory.observe_ram(8000000000)
        self.assertIsNone(value.total_bytes)
        self.assertIsNone(value.available_bytes)
        self.assertFalse(value.fits_observed_ram)
        self.assertEqual(value.source,"unknown")
        self.assertFalse(value.to_record()["native_model_started"])

    def test_windows_branch_is_read_only_and_labeled(self):
        with (
            mock.patch.object(memory.os,"name","nt"),
            mock.patch.object(memory,"_windows_physical",return_value=(16<<30, 10<<30)),
        ):
            value = memory.observe_ram(8<<30)
        self.assertTrue(value.fits_observed_ram)
        self.assertEqual(value.source,"windows_physical")
        self.assertFalse(value.to_record()["physical_device_qualified"])

    def test_corrupt_platform_values_cannot_pass(self):
        for raw in ((0,0),(8,-1),(10,11),(True,8),("16",8)):
            with self.subTest(raw=raw):
                with (
                    mock.patch.object(memory.os,"name","posix"),
                    mock.patch.object(memory,"_posix_physical",return_value=raw),
                ):
                    value = memory.observe_ram(2)
                self.assertEqual(value.source,"unknown")
                self.assertFalse(value.fits_observed_ram)
