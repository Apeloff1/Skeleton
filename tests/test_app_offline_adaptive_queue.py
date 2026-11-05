"""Local indexing queue uses current hardware instead of stored job quotas."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from skeleton.app.offline_resources import LocalResourceSnapshot
from skeleton.app import offline_index_queue
from skeleton.app.offline_index_queue import OfflineIndexQueue


class LocalAdaptiveQueueTests(unittest.TestCase):
    def test_more_than_legacy_stored_job_limit_is_admitted(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for item in ("a", "b"):
                (root / item).mkdir()
            with OfflineIndexQueue(root / "jobs.sqlite") as queue:
                with patch.object(offline_index_queue, "MAX_STORED_JOBS", 1):
                    queue.enqueue(root / "a", root / "library.sqlite")
                    queue.enqueue(root / "b", root / "library.sqlite")
                self.assertEqual(len(queue.list_jobs()), 2)

    def test_default_drain_adapts_to_measured_headroom(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for item in ("a", "b", "c", "d"):
                (root / item).mkdir()
                (root / item / "source.txt").write_text(item + " indexing.")
            with OfflineIndexQueue(root / "jobs.sqlite") as queue:
                for item in ("a", "b", "c", "d"):
                    queue.enqueue(root / item, root / "library.sqlite")
                low = LocalResourceSnapshot(
                    total_ram_bytes=1_000_000_000, available_ram_bytes=100_000_000,
                    total_disk_bytes=100_000_000_000, free_disk_bytes=50_000_000_000,
                    cpu_count=8, cpu_load_ratio=0.95,
                )
                high = LocalResourceSnapshot(
                    total_ram_bytes=1_000_000_000, available_ram_bytes=800_000_000,
                    total_disk_bytes=100_000_000_000, free_disk_bytes=50_000_000_000,
                    cpu_count=8, cpu_load_ratio=0,
                )
                with patch.object(offline_index_queue, "probe_local_resources",
                                  return_value=low):
                    self.assertEqual(len(queue.drain()), 1)
                with patch.object(offline_index_queue, "probe_local_resources",
                                  return_value=high):
                    self.assertEqual(len(queue.drain()), 3)


if __name__ == "__main__":
    unittest.main()
