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

    def test_remove_existing_bad_file(self):
        old = "legacy/con.txt"
        self.assertEqual(check_paths({old}, set()), [])


if __name__ == "__main__":
    unittest.main()
