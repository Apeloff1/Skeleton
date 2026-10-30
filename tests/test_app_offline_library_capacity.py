"""Local-only capacity: source length and file count are not service quotas."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from skeleton.app import offline_library
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
