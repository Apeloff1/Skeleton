"""Godot resource path custody across POSIX and Windows-style input."""
import tempfile
import unittest
from pathlib import Path

from skeleton.godot_export.project import path_to_res, res_to_path, GodotProject


class GodotResourceBoundaryTests(unittest.TestCase):
    def test_valid_nested_resource_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "scenes" / "first.tscn"
            target.parent.mkdir()
            target.write_text("[gd_scene format=3]", encoding="utf-8")
            self.assertEqual(res_to_path(root, "res://scenes/first.tscn"), target)
            self.assertEqual(path_to_res(root, target), "res://scenes/first.tscn")

    def test_rejects_traversal_and_cross_platform_spelling(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for value in ("res://../outside", "res://a/../b", "res:///etc/passwd",
                          "res://a//b", "res://./b", "res://",
                          "res://C:/windows", "res://a\\\\..\\\\secret",
                          "res://a\\\\b", "file:///tmp/x", "res://a\\x00b"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    res_to_path(root, value)

    def test_symlink_file_and_parent_escape_are_denied(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            root = Path(d)
            external = Path(outside) / "private.tscn"
            external.write_text("private", encoding="utf-8")
            for link, target in ((root / "linked.tscn", external),
                                 (root / "linked_dir", Path(outside))):
                try:
                    link.symlink_to(target, target_is_directory=target.is_dir())
                except (OSError, NotImplementedError):
                    self.skipTest("symlinks unavailable on host")
                with self.assertRaises(ValueError):
                    res_to_path(root, "res://" + link.name +
                                ("/private.tscn" if target.is_dir() else ""))
                with self.assertRaises(ValueError):
                    path_to_res(root, link)
            self.assertFalse(GodotProject(root, None).exists("res://linked.tscn"))

    def test_missing_resource_stays_within_project(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(res_to_path(root, "res://new/scene.tscn"),
                             root / "new" / "scene.tscn")
            self.assertFalse(GodotProject(root, None).exists("res://new/scene.tscn"))


if __name__ == "__main__":
    unittest.main()
