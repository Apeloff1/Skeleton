"""Live hardware budget calculations, independent of a particular host."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from skeleton.app.offline_resources import (
    LocalResourcePressure, LocalResourceSnapshot,
    _linux_memory, _linux_swap, admit_resident_document, admit_disk_document,
    probe_local_resources,
)


class LocalResourceBudgetTests(unittest.TestCase):
    def snapshot(self, *, memory: int, disk: int, load: float = 0.0):
        return LocalResourceSnapshot(
            total_ram_bytes=16_000_000_000, available_ram_bytes=memory,
            total_disk_bytes=1_000_000_000_000, free_disk_bytes=disk,
            cpu_count=8, cpu_load_ratio=load,
        )

    def test_live_ram_changes_admission_without_static_file_quota(self):
        payload_size = 100_000_000
        plenty = self.snapshot(memory=8_000_000_000, disk=300_000_000_000)
        tight = self.snapshot(memory=200_000_000, disk=300_000_000_000)
        admit_resident_document(plenty, payload_size)
        with self.assertRaisesRegex(LocalResourcePressure, "RAM"):
            admit_resident_document(tight, payload_size)
        self.assertLess(tight.resident_document_budget,
                        plenty.resident_document_budget)

    def test_free_disk_changes_writes_but_not_unmodified_reads(self):
        enough = self.snapshot(memory=8_000_000_000, disk=300_000_000_000)
        low = self.snapshot(memory=8_000_000_000, disk=2_000_000_000)
        admit_resident_document(enough, 100_000_000, write=True)
        admit_resident_document(low, 100_000_000, write=False)
        with self.assertRaisesRegex(LocalResourcePressure, "disk"):
            admit_resident_document(low, 100_000_000, write=True)

    def test_load_adapts_processing_buffers_and_admission_batch(self):
        quiet = self.snapshot(memory=8_000_000_000, disk=300_000_000_000)
        busy = self.snapshot(memory=8_000_000_000, disk=300_000_000_000,
                             load=0.95)
        self.assertGreater(quiet.read_chunk_bytes, busy.read_chunk_bytes)
        self.assertGreater(quiet.suggested_index_jobs,
                           busy.suggested_index_jobs)

    def test_container_memory_ceiling_overrides_host(self):
        meminfo = "MemTotal:       16000000 kB\nMemAvailable:  12000000 kB\n"
        counters = {
            "/sys/fs/cgroup/memory.max": 2_000_000_000,
            "/sys/fs/cgroup/memory.current": 1_500_000_000,
        }
        from unittest.mock import mock_open
        from skeleton.app import offline_resources
        def counter(path):
            return counters.get(str(path))
        with patch("builtins.open", mock_open(read_data=meminfo)), \
             patch.object(offline_resources, "_read_counter", side_effect=counter):
            self.assertEqual(_linux_memory(), (2_000_000_000, 500_000_000))

    def test_cpu_quota_is_respected(self):
        from unittest.mock import mock_open
        from skeleton.app import offline_resources
        with TemporaryDirectory() as temp:
            with patch.object(offline_resources, "_linux_memory",
                              return_value=(8_000_000_000, 4_000_000_000)), \
                 patch.object(offline_resources.os, "cpu_count", return_value=12), \
                 patch.object(offline_resources.Path, "read_text",
                              return_value="150000 100000"):
                snap = probe_local_resources(temp)
            self.assertEqual(snap.cpu_count, 2)

    def test_swap_is_a_pressure_signal_not_extra_free_ram(self):
        plenty = self.snapshot(memory=2_000_000_000, disk=10_000_000_000)
        committed = LocalResourceSnapshot(
            total_ram_bytes=plenty.total_ram_bytes,
            available_ram_bytes=plenty.available_ram_bytes,
            total_disk_bytes=plenty.total_disk_bytes,
            free_disk_bytes=plenty.free_disk_bytes,
            cpu_count=8, cpu_load_ratio=0.1,
            total_swap_bytes=8_000_000_000,
            free_swap_bytes=200_000_000,
            memory_pressure_ratio=0.35,
        )
        self.assertTrue(committed.should_spill_early)
        self.assertLess(committed.resident_document_budget,
                        plenty.resident_document_budget)
        self.assertLess(committed.suggested_index_jobs,
                        plenty.suggested_index_jobs)
        admit_disk_document(committed, 5_000_000)
        with self.assertRaisesRegex(LocalResourcePressure, "RAM"):
            admit_resident_document(committed, 200_000_000)

    def test_cgroup_swap_ceiling_is_respected(self):
        from unittest.mock import mock_open
        from skeleton.app import offline_resources
        meminfo = "SwapTotal: 4000000 kB\nSwapFree: 3000000 kB\n"
        counters = {
            "/sys/fs/cgroup/memory.swap.max": 1_000_000_000,
            "/sys/fs/cgroup/memory.swap.current": 800_000_000,
        }
        with (
            patch("builtins.open", mock_open(read_data=meminfo)),
            patch.object(offline_resources, "_read_counter",
                         side_effect=lambda p: counters.get(str(p))),
        ):
            self.assertEqual(_linux_swap(), (1_000_000_000, 200_000_000))

    def test_probe_reports_host_disk_and_recomputes(self):
        with TemporaryDirectory() as temp:
            with patch("skeleton.app.offline_resources._linux_memory",
                       return_value=(8_000_000_000, 4_000_000_000)):
                result = probe_local_resources(Path(temp))
            self.assertGreater(result.read_chunk_bytes, 0)
            self.assertGreater(result.free_disk_bytes, 0)
            self.assertGreaterEqual(result.cpu_count, 1)


if __name__ == "__main__":
    unittest.main()
