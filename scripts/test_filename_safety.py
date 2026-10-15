"""Regression checks for portable, unambiguous repository filenames."""

import unittest

from scripts.check_filename_safety import check_paths, unsafe_filename


class FilenameSafetyTests(unittest.TestCase):
    def test_valid_new_path(self):
        self.assertEqual(check_paths(set(), {"scripts/new_file.py"}), [])

    def test_case_only_leaf_collision(self):
        issues = check_paths({"a/Foo.py"}, {"a/Foo.py", "a/foo.py"})
        self.assertTrue(any("collision" in issue for issue in issues), issues)

    def test_case_only_directory_collision(self):
        issues = check_paths(set(), {"Assets/icon.png", "assets/readme.md"})
        self.assertTrue(any("collision" in issue for issue in issues), issues)

    def test_unicode_equivalent_collision(self):
        issues = check_paths(set(), {"docs/café.md", "docs/cafe\u0301.md"})
        self.assertTrue(any("collision" in issue for issue in issues), issues)

    def test_file_directory_collision(self):
        issues = check_paths(set(), {"guide", "Guide/readme.md"})
        self.assertTrue(any("collision" in issue for issue in issues), issues)

    def test_windows_reserved(self):
        for name in ("aux.txt", "COM1", "NUL.json", "lpt9.log"):
            with self.subTest(name=name):
                self.assertTrue(unsafe_filename("folder/" + name))

    def test_windows_invalid(self):
        for name in ("bad:name", "bad?.txt", "bad .", "bad\\name"):
            with self.subTest(name=name):
                self.assertTrue(unsafe_filename("folder/" + name))

    def test_old_long_path_grandfathered(self):
        long_path = "archive/" + "e" * 235 + ".json"
        self.assertEqual(check_paths({long_path}, {long_path}), [])
        self.assertTrue(check_paths(set(), {long_path}))

    def test_renaming_old_long_path_is_checked(self):
        old = "archive/" + "f" * 235 + ".txt"
        new = "archive/" + "g" * 235 + ".txt"
        self.assertTrue(check_paths({old}, {new}))

    def test_legacy_case_directory_collision_is_grandfathered(self):
        paths = {"snapshots/components/UI/index.ts", "snapshots/components/ui/icon.ts"}
        self.assertEqual(check_paths(paths, paths), [])

    def test_new_file_beneath_legacy_colliding_dir_is_rejected(self):
        previous = {"snapshots/components/UI/index.ts", "snapshots/components/ui/icon.ts"}
        current = previous | {"snapshots/components/ui/another.ts"}
        issues = check_paths(previous, current)
        self.assertTrue(any("ambiguous" in issue for issue in issues), issues)

    def test_unrelated_new_file_with_old_collision_is_allowed(self):
        previous = {"snapshots/components/UI/index.ts", "snapshots/components/ui/icon.ts"}
        current = previous | {"scripts/portable.py"}
        self.assertEqual(check_paths(previous, current), [])

    def test_removing_legacy_collision_is_safe(self):
        previous = {"snapshots/components/UI/index.ts", "snapshots/components/ui/icon.ts"}
        current = {"snapshots/components/UI/index.ts"}
        self.assertEqual(check_paths(previous, current), [])

    def test_utf16_length_not_just_python_character_count(self):
        # Non-BMP codepoints count twice toward the classic Windows MAX_PATH.
        name = "😀" * 45 + "/" + "😀" * 45 + "/" + "😀" * 40
        self.assertLess(len(name), 240)
        self.assertTrue(any("UTF-16" in issue for issue in unsafe_filename(name)))

    def test_windows_extended_reserved_devices(self):
        for name in ("COM¹", "COM².txt", "LPT³.log", "CONIN$", "CONOUT$.txt"):
            with self.subTest(name=name):
                self.assertTrue(
                    any("reserved Windows" in issue for issue in unsafe_filename("folder/" + name))
                )

    def test_utf8_path_budget_with_short_utf16_name(self):
        path = "data/" + "漢" * 90 + ".json"
        self.assertLess(len(path), 240)
        issues = unsafe_filename(path)
        self.assertTrue(any("UTF-8" in issue for issue in issues), issues)

    def test_legacy_utf8_long_path_remains_unchanged(self):
        path = "legacy/" + "漢" * 90 + ".json"
        self.assertEqual(check_paths({path}, {path}), [])
        self.assertTrue(check_paths(set(), {path}))

    def test_utf8_boundary_allows_portable_path(self):
        path = "data/" + "a" * 229 + ".json"
        self.assertEqual(unsafe_filename(path), [])

    def test_remove_existing_bad_file(self):
        old = "legacy/con.txt"
        self.assertEqual(check_paths({old}, set()), [])


if __name__ == "__main__":
    unittest.main()
