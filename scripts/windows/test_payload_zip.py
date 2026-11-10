"""Focused checks for Windows installer archive admission (no extraction)."""

from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from scripts.windows.check_payload_zip import (
    MAX_ENTRIES,
    MAX_UNCOMPRESSED_BYTES,
    archive_errors,
    filename_errors,
    inspect_zip,
)


class PayloadZipPreflightTests(unittest.TestCase):
    def test_valid_archive_and_exact_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "payload.zip"
            with ZipFile(archive, "w") as target:
                target.writestr("skeleton/app/manifest.json", '{"ok": true}')
                target.writestr("backend/main.py", "print('ok')")
            count, size, failures = inspect_zip(archive)
            self.assertEqual(count, 2)
            self.assertEqual(size, len('{"ok": true}') + len("print('ok')"))
            self.assertEqual(failures, [])

    def test_invalid_windows_and_reserved_names(self) -> None:
        for path in (
            "backend/CON.txt",
            "frontend/AUX",
            "docs/CLOCK$.md",
            "docs/file?.md",
            "docs/trailing. ",
            "scripts/.git/config",
            "docs/\u202esecret.txt",
        ):
            with self.subTest(path=path):
                self.assertTrue(filename_errors(path))

    def test_absolute_or_traversal_paths_rejected(self) -> None:
        for path in ("/root/secret", "../escape.txt", "docs/../escape", "a//b", "a\\b"):
            with self.subTest(path=path):
                self.assertTrue(filename_errors(path))

    def test_utf8_length_guard_catches_multibyte_names(self) -> None:
        name = "assets/" + ("é" * 95) + ".png"
        self.assertLess(len(name), 190)
        self.assertTrue(any("UTF-8" in issue for issue in filename_errors(name)))

    def test_utf16_length_guard_catches_non_bmp_names(self) -> None:
        name = "assets/" + ("😀" * 91) + ".png"
        self.assertLess(len(name), 190)
        self.assertTrue(any("UTF-16" in issue for issue in filename_errors(name)))

    def test_default_install_destination_ceiling(self) -> None:
        root = "C:\\Users\\" + "x" * 32 + "\\AppData\\Local\\Programs\\Skeleton"
        entry = "nested/" + ("n" * 165) + ".py"
        self.assertEqual(filename_errors(entry), [])
        self.assertTrue(
            any("default installed" in error for error in filename_errors(entry, install_root=root))
        )

    def test_case_collisions_in_parent_directory(self) -> None:
        issues = archive_errors([ZipInfo("Assets/a.png"), ZipInfo("assets/b.png")])
        self.assertTrue(any("collision" in issue for issue in issues), issues)

    def test_unicode_normalization_collision(self) -> None:
        issues = archive_errors([ZipInfo("café/info.txt"), ZipInfo("cafe\u0301/icon.txt")])
        self.assertTrue(any("collision" in issue for issue in issues), issues)

    def test_file_directory_conflict(self) -> None:
        issues = archive_errors([ZipInfo("game/Assets"), ZipInfo("game/assets/logo.png")])
        self.assertTrue(any("collision" in issue for issue in issues), issues)

    def test_duplicate_zip_file_entry(self) -> None:
        issues = archive_errors([ZipInfo("same.txt"), ZipInfo("same.txt")])
        self.assertTrue(any("duplicate" in issue for issue in issues), issues)

    def test_symlink_rejected(self) -> None:
        info = ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.assertTrue(any("unsupported Unix special file type" in issue for issue in archive_errors([info])))

    def test_unix_special_inode_types_fail_closed(self) -> None:
        for inode in (stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFLNK):
            with self.subTest(inode=inode):
                entry = ZipInfo("payload/special")
                entry.create_system = 3
                entry.external_attr = (inode | 0o600) << 16
                self.assertTrue(
                    any("unsupported Unix special file type" in error for error in archive_errors([entry]))
                )

    def test_unix_directory_and_file_metadata_mismatch(self) -> None:
        directory_without_suffix = ZipInfo("payload/dir")
        directory_without_suffix.create_system = 3
        directory_without_suffix.external_attr = (stat.S_IFDIR | 0o755) << 16
        file_with_suffix = ZipInfo("payload/file/")
        file_with_suffix.create_system = 3
        file_with_suffix.external_attr = (stat.S_IFREG | 0o644) << 16
        self.assertTrue(any("directory mode" in e for e in archive_errors([directory_without_suffix])))
        self.assertTrue(any("regular file mode" in e for e in archive_errors([file_with_suffix])))

    def test_regular_unix_file_and_directory_allowed(self) -> None:
        directory = ZipInfo("payload/")
        directory.create_system = 3
        directory.external_attr = (stat.S_IFDIR | 0o755) << 16
        regular = ZipInfo("payload/main.py")
        regular.create_system = 3
        regular.external_attr = (stat.S_IFREG | 0o644) << 16
        self.assertEqual(archive_errors([directory, regular]), [])

    def test_huge_entry_rejected_without_allocating(self) -> None:
        info = ZipInfo("big.bin")
        info.file_size = MAX_UNCOMPRESSED_BYTES + 1
        self.assertTrue(any("bytes" in issue for issue in archive_errors([info])))

    def test_entry_ceiling_bounded(self) -> None:
        info = ZipInfo("same.txt")
        # Counting is bounded even if a ZIP carries a very large directory.
        self.assertTrue(any("entries" in issue for issue in archive_errors([info] * (MAX_ENTRIES + 1))))

    def test_empty_archive_rejected(self) -> None:
        self.assertTrue(archive_errors([]))


if __name__ == "__main__":
    unittest.main()
