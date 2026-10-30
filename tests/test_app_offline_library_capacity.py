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

    def test_current_memory_pressure_automatically_spills_to_disk(self):
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
                    outcome = library.index_directory(source)
                self.assertEqual(outcome["offloaded_files"], 1)
                self.assertEqual(library.count(), 1)
                self.assertTrue(library.search("admission"))
                with patch.object(offline_library, "probe_local_resources",
                                  return_value=plentiful):
                    outcome = library.index_directory(source)
                self.assertEqual(outcome["offloaded_files"], 0)
                self.assertTrue(library.search("admission"))
                self.assertEqual(library._db.execute(
                    "SELECT COUNT(*) FROM offline_document_chunks"
                ).fetchone()[0], 0)

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

    def test_swap_pressure_spills_and_preserves_utf8_and_full_digest(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "sources"
            source.mkdir()
            # UTF-8 code points and search terms cross arbitrary read buffers.
            body = ("the renderer uses rasterização and memory mapped pages. " * 2500)
            body += "uniquetermatsourceend"
            (source / "large.txt").write_text(body, encoding="utf-8")
            disk_pressure = LocalResourceSnapshot(
                total_ram_bytes=8_000_000_000,
                available_ram_bytes=100_000_000,
                total_disk_bytes=1_000_000_000_000,
                free_disk_bytes=500_000_000_000,
                cpu_count=8,
                cpu_load_ratio=0.75,
                total_swap_bytes=2_000_000_000,
                free_swap_bytes=10_000_000,
                memory_pressure_ratio=0.4,
            )
            with OfflineDocumentLibrary(root / "index.sqlite") as library:
                with patch.object(offline_library, "probe_local_resources",
                                  return_value=disk_pressure):
                    outcome = library.index_directory(source)
                    self.assertEqual(outcome["offloaded_files"], 1)
                    self.assertEqual(outcome["offloaded_bytes"],
                                     len(body.encode("utf-8")))
                    self.assertEqual(library.index_directory(source)["updated_files"], 0)
                hits = library.search("uniquetermatsourceend")
                self.assertEqual(len(hits), 1)
                self.assertIn("uniquetermatsourceend", hits[0].excerpt)
                self.assertEqual(hits[0].document_sha256,
                                 __import__("hashlib").sha256(
                                     body.encode("utf-8")).hexdigest())

    def test_disk_spill_integrity_tamper_fails_closed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "sources"
            source.mkdir()
            (source / "book.txt").write_text(
                "verifieddiskchunk uniqueanswer " * 1400, encoding="utf-8")
            tight = LocalResourceSnapshot(
                total_ram_bytes=1_000_000_000, available_ram_bytes=100_000,
                total_disk_bytes=1_000_000_000_000, free_disk_bytes=500_000_000_000,
                cpu_count=4, cpu_load_ratio=0.9,
            )
            with OfflineDocumentLibrary(root / "index.sqlite") as library:
                with patch.object(offline_library, "probe_local_resources",
                                  return_value=tight):
                    library.index_directory(source)
                self.assertTrue(library.search("verifieddiskchunk"))
                library._db.execute(
                    "UPDATE offline_document_chunks SET body='tampered' "
                    "WHERE ordinal=0"
                )
                with self.assertRaisesRegex(OfflineLibraryError,
                                            "integrity verification"):
                    library.search("uniqueanswer")
                with patch.object(offline_library, "probe_local_resources",
                                  return_value=tight):
                    self.assertEqual(library.index_directory(source)["updated_files"], 1)
                self.assertTrue(library.search("verifieddiskchunk"))

    def test_spill_rejects_low_disk_without_losing_previous_snapshot(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "sources"
            source.mkdir()
            (source / "book.txt").write_text("original verified data")
            with OfflineDocumentLibrary(root / "index.sqlite") as library:
                library.index_directory(source)
                (source / "book.txt").write_text("new disk-backed content " * 1200)
                low = LocalResourceSnapshot(
                    total_ram_bytes=1_000_000_000, available_ram_bytes=100_000,
                    total_disk_bytes=100_000_000_000, free_disk_bytes=100_000,
                    cpu_count=4, cpu_load_ratio=0.8,
                )
                with patch.object(offline_library, "probe_local_resources",
                                  return_value=low):
                    with self.assertRaisesRegex(OfflineLibraryError, "disk"):
                        library.index_directory(source)
                self.assertEqual(library.count(), 1)
                self.assertTrue(library.search("original"))
                self.assertFalse(library.search("backed"))

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
