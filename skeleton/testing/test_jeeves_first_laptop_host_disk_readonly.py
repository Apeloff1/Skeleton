"""Storage headroom checks are read-only and not installer/device proof."""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.jeeves.native_fabric.laptop_ops.host_probes import disk

class DiskReadOnlyTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "POSIX descriptor anchoring only")
    def test_real_directory_fstatvfs_uses_no_state_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            before = tuple(root.iterdir())
            result = disk.observe_disk(root, 1024)
            after = tuple(root.iterdir())
        self.assertEqual(before,after)
        self.assertEqual(result.source,"posix_fstatvfs")
        self.assertTrue(result.fits_observed_space)
        self.assertTrue(result.to_record()["final_directory_descriptor_anchored"])
        self.assertFalse(result.to_record()["filesystem_custody_qualified"])
        self.assertFalse(result.to_record()["native_model_started"])

    @unittest.skipUnless(os.name == "posix", "POSIX O_NOFOLLOW regression")
    def test_final_component_symlink_cannot_be_probed(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            real = parent / "actual"
            real.mkdir()
            alias = parent / "alias"
            alias.symlink_to(real, target_is_directory=True)
            result = disk.observe_disk(alias, 10)
        self.assertIsNone(result.available_bytes)
        self.assertEqual(result.source,"unknown")
        self.assertFalse(result.fits_observed_space)

    def test_unknown_or_nonexistent_storage_is_held(self):
        with tempfile.TemporaryDirectory() as temp:
            unknown = Path(temp) / "nonexistent"
            snapshot = disk.observe_disk(unknown, 100)
        self.assertEqual(snapshot.source,"unknown")
        self.assertFalse(snapshot.to_record()["release_certified"])

    def test_windows_metadata_is_explicitly_non_anchored(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)  # Construct native platform Path before OS mock.
            with (
                mock.patch.object(disk.os,"name","nt"),
                mock.patch.object(disk,"_windows_disk",return_value=(1000,750)),
            ):
                snapshot = disk.observe_disk(path,500)
        self.assertTrue(snapshot.fits_observed_space)
        self.assertEqual(snapshot.source,"windows_disk_usage")
        self.assertFalse(snapshot.to_record()["final_directory_descriptor_anchored"])
        self.assertFalse(snapshot.to_record()["physical_device_qualified"])
