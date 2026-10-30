"""Local-only capacity: source length and file count are not service quotas."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from skeleton.app import offline_library
from skeleton.app.offline_resources import LocalResourceSnapshot
from skeleton.app.offline_library import OfflineDocumentLibrary, OfflineLibraryError


class LocalCapacityTests(unittest.TestCase):
    def test_document_larger_than_legacy_128kib_and_no_legacy_corpus_quota(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            body = "Offline indexing full-document fidelity. " * 5000
            (source / "large.txt").write_text(body, encoding="utf-8")
            (source / "second.md").write_text("This file is searchable.", encoding="utf-8")
            with patch.object(offline_library, "MAX_FILES", 1), \
                 patch.object(offline_library, "MAX_DOCUMENT_BYTES", 1), \
                 patch.object(offline_library, "MAX_TOTAL_BYTES", 1), \
                 patch.object(offline_library, "MAX_LIBRARY_FILES", 1), \
                 patch.object(offline_library, "MAX_LIBRARY_BYTES", 1):
                with OfflineDocumentLibrary(root / "index.sqlite") as library:
                    outcome = library.index_directory(source)
                    self.assertEqual(outcome["indexed_files"], 2)
                    self.assertGreater(outcome["indexed_bytes"], 131072)
                    self.assertEqual(library.count(), 2)
                    self.assertTrue(library.search("fidelity"))
                    self.assertEqual(library.index_directory(source)["updated_files"], 0)

    def test_current_memory_pressure_blocks_only_unsafe_resident_work(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "large.txt").write_text("Local memory admission " * 2000)
            plentiful = LocalResourceSnapshot(
                total_ram_bytes=2_000_000_000, available_ram_bytes=1_000_000_000,
                total_disk_bytes=100_000_000_000, free_disk_bytes=50_000_000_000,
                cpu_count=8, cpu_load_ratio=0.1,
            )
            tight = LocalResourceSnapshot(
                total_ram_bytes=2_000_000_000, available_ram_bytes=100_000,
                total_disk_bytes=100_000_000_000, free_disk_bytes=50_000_000_000,
                cpu_count=8, cpu_load_ratio=0.9,
            )
            with OfflineDocumentLibrary(root / "index.sqlite") as library:
                with patch.object(offline_library, "probe_local_resources",
                                  return_value=tight):
                    with self.assertRaisesRegex(OfflineLibraryError, "RAM"):
                        library.index_directory(source)
                self.assertEqual(library.count(), 0)
                with patch.object(offline_library, "probe_local_resources",
                                  return_value=plentiful):
                    self.assertEqual(library.index_directory(source)["indexed_files"], 1)

    def test_current_disk_pressure_rolls_back_updates(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "large.txt").write_text("Disk pressure must not commit." * 300)
            abundant = LocalResourceSnapshot(
                total_ram_bytes=2_000_000_000, available_ram_bytes=1_000_000_000,
                total_disk_bytes=1_000_000_000, free_disk_bytes=800_000_000,
                cpu_count=4, cpu_load_ratio=0,
            )
            full = LocalResourceSnapshot(
                total_ram_bytes=2_000_000_000, available_ram_bytes=1_000_000_000,
                total_disk_bytes=1_000_000_000, free_disk_bytes=1_000_000,
                cpu_count=4, cpu_load_ratio=0,
            )
            with OfflineDocumentLibrary(root / "index.sqlite") as library:
                with patch.object(offline_library, "probe_local_resources",
                                  return_value=abundant):
                    library.index_directory(source)
                (source / "large.txt").write_text("Changed content." * 300)
                with patch.object(offline_library, "probe_local_resources",
                                  return_value=full):
                    with self.assertRaisesRegex(OfflineLibraryError, "disk"):
                        library.index_directory(source)
                self.assertTrue(library.search("Disk"))
                self.assertFalse(library.search("Changed"))

    def test_invalid_source_rolls_back_entire_snapshot(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "good.txt").write_text("Original source", encoding="utf-8")
            with OfflineDocumentLibrary(root / "index.sqlite") as library:
                library.index_directory(source)
                (source / "good.txt").write_text("Mutation that must not commit", encoding="utf-8")
                (source / "z-bad.txt").write_bytes(b"\xff\xfe")
                with self.assertRaises(OfflineLibraryError):
                    library.index_directory(source)
                self.assertEqual(library.count(), 1)
                self.assertTrue(library.search("Original"))
                self.assertFalse(library.search("Mutation"))


if __name__ == "__main__":
    unittest.main()
