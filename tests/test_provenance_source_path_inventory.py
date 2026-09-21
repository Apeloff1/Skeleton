from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_source_path_inventory.py"
SPEC = importlib.util.spec_from_file_location("check_source_path_inventory", SCRIPT)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


LIVE_EXAMPLES = (
    ("skeleton/kernel/capabilities.py", "canonical"),
    ("backend/server.py", "canonical"),
    ("frontend/package.json", "canonical"),
    ("core/activation_security.py", "canonical"),
    ("skeleton/testing/test_backlog_reader.py", "first-party"),
    ("backend/tests/test_architecture_boundaries.py", "first-party"),
    ("scripts/check_architecture_boundaries.py", "first-party"),
    ("tests/test_architecture_boundaries.py", "first-party"),
    ("docs/CANONICAL_MODULE_BOUNDARIES.md", "first-party"),
    (".github/workflows/provenance-policy.yml", "first-party"),
    (".machine/README.md", "first-party"),
    (".machine/repository.toml", "first-party"),
    ("machine/README.md", "first-party"),
    ("machine/manifest.json", "first-party"),
    ("packaging/windows/SkeletonSetup.iss", "first-party"),
    ("packaging/windows/launcher_entry.py", "first-party"),
    ("README.md", "first-party"),
    ("satellites/gameforge-middleware/README.md", "first-party"),
    ("skeleton/testing/data/frontier_npc_source_fixture.json", "fixture"),
    ("frontend/assets/images/icon.png", "binary"),
    ("backend/godot.artifact.json", "canonical"),
    ("memory/mongo_backup/test_database/academy_subjects.bson", "generated"),
    ("backend/data/vault/compressed/_manifest.json", "generated"),
    ("satellites/branch-snapshots/README.md", "archive"),
    ("docs/archive/SEVEN_BY_INDEX.md", "archive"),
    ("tests/legacy_root/backend_test.py", "archive"),
    ("scripts/legacy_root/README.md", "archive"),
)


class SourcePathInventoryTests(unittest.TestCase):
    def test_java_accelerators_are_first_party_not_canonical(self) -> None:
        for path in (
            "java-accelerators/observability/AcceleratorMain.java",
            "java-accelerators/vector/VectorSearchMain.java",
            "java-accelerators/physics/BroadPhaseMain.java",
        ):
            self.assertEqual(policy.classify_path(path), "first-party")

    def test_closed_class_set_is_ordered_and_exclusive(self) -> None:
        self.assertEqual(
            policy.CLASSES,
            (
                "archive",
                "vendor",
                "generated",
                "fixture",
                "binary",
                "canonical",
                "first-party",
            ),
        )
        self.assertEqual(len(policy.CLASSES), len(set(policy.CLASSES)))

    def test_archive_wins_over_canonical_and_binary(self) -> None:
        self.assertEqual(
            policy.classify_path("satellites/branch-snapshots/old/skeleton/kernel/x.py"),
            "archive",
        )
        self.assertEqual(
            policy.classify_path("satellites/branch-snapshots/old/frontend/assets/icon.png"),
            "archive",
        )
        self.assertEqual(policy.classify_path("docs/archive/planning/SEVEN_BY_42.md"), "archive")
        self.assertEqual(policy.classify_path("tests/legacy_root/backend_test.py"), "archive")
        self.assertEqual(policy.classify_path("scripts/legacy_root/backend_sweep.py"), "archive")

    def test_vendor_wins_over_canonical(self) -> None:
        self.assertEqual(policy.classify_path("frontend/node_modules/react/index.js"), "vendor")
        self.assertEqual(policy.classify_path("skeleton/vendor/third.py"), "vendor")
        self.assertEqual(policy.classify_path("backend/third_party/lib.py"), "vendor")

    def test_skeleton_build_package_is_canonical_not_generated(self) -> None:
        self.assertEqual(
            policy.classify_path("skeleton/build/incremental_graph.py"),
            "canonical",
        )
        self.assertEqual(policy.classify_path("build/lib/generated.py"), "generated")
        self.assertEqual(policy.classify_path("frontend/build/bundle.js"), "generated")
        self.assertEqual(policy.classify_path("backend/build/cache.bin"), "generated")

    def test_generated_wins_over_binary_and_canonical(self) -> None:
        self.assertEqual(
            policy.classify_path("memory/mongo_backup/test_database/academy_subjects.bson"),
            "generated",
        )
        self.assertEqual(
            policy.classify_path("backend/data/vault/compressed/ai-goap.jsonl.zst"),
            "generated",
        )
        self.assertEqual(policy.classify_path("skeleton/__pycache__/kernel.cpython-311.pyc"), "generated")
        self.assertEqual(policy.classify_path("frontend/dist/bundle.js"), "generated")
        self.assertEqual(policy.classify_path("pkg.egg-info/PKG-INFO"), "generated")
        self.assertEqual(policy.classify_path("test_result.md"), "generated")

    def test_fixture_wins_over_first_party_tests_and_canonical(self) -> None:
        self.assertEqual(
            policy.classify_path("skeleton/testing/data/frontier_npc_source_fixture.json"),
            "fixture",
        )
        self.assertEqual(policy.classify_path("tests/fixtures/sample.json"), "fixture")
        self.assertEqual(policy.classify_path("backend/tests/testdata/world.json"), "fixture")
        self.assertEqual(policy.classify_path("skeleton/testing/fixture_world.json"), "fixture")

    def test_binary_wins_over_canonical(self) -> None:
        self.assertEqual(policy.classify_path("frontend/assets/images/icon.png"), "binary")
        self.assertEqual(policy.classify_path("backend/godot"), "binary")
        self.assertEqual(policy.classify_path("docs/diagram.pdf"), "binary")

    def test_canonical_production_trees(self) -> None:
        self.assertEqual(policy.classify_path("skeleton/kernel/capabilities.py"), "canonical")
        self.assertEqual(policy.classify_path("backend/server.py"), "canonical")
        self.assertEqual(policy.classify_path("frontend/src/app.tsx"), "canonical")
        self.assertEqual(policy.classify_path("core/runtime.py"), "canonical")

    def test_first_party_excludes_canonical_production_and_archive(self) -> None:
        self.assertEqual(policy.classify_path("skeleton/testing/fixtures.py"), "first-party")
        self.assertEqual(policy.classify_path("backend/tests/test_architecture_boundaries.py"), "first-party")
        self.assertEqual(policy.classify_path("scripts/check_source_path_inventory.py"), "first-party")
        self.assertEqual(policy.classify_path("tests/test_provenance_source_path_inventory.py"), "first-party")
        self.assertEqual(policy.classify_path("docs/CANONICAL_MODULE_BOUNDARIES.md"), "first-party")
        self.assertEqual(policy.classify_path(".github/workflows/ci.yml"), "first-party")
        self.assertEqual(policy.classify_path(".machine/README.md"), "first-party")
        self.assertEqual(policy.classify_path(".machine/repository.toml"), "first-party")
        self.assertEqual(policy.classify_path("machine/README.md"), "first-party")
        self.assertEqual(policy.classify_path("machine/manifest.json"), "first-party")
        self.assertEqual(policy.classify_path("packaging/windows/SkeletonSetup.iss"), "first-party")
        self.assertEqual(policy.classify_path("packaging/windows/launcher_entry.py"), "first-party")
        self.assertEqual(policy.classify_path("satellites/gameforge-middleware/README.md"), "first-party")
        self.assertEqual(policy.classify_path("README.md"), "first-party")
        self.assertEqual(policy.classify_path("memory/PRD.md"), "first-party")

    def test_invalid_paths_are_unknown_not_canonical(self) -> None:
        for path in (
            "",
            "/etc/passwd",
            "../secret.py",
            "skeleton//kernel.py",
            "skeleton\\kernel.py",
            "skeleton/./kernel.py",
            None,
            12,
        ):
            self.assertEqual(policy.classify_path(path), "unknown")

    def test_unknown_paths_fail_closed(self) -> None:
        errors = policy.validate_source_path_inventory(["mystery/module.py", "unreviewed/scratch_marker.txt"])
        self.assertTrue(any("mystery/module.py: unclassified source path" in error for error in errors))
        self.assertTrue(any("unreviewed/scratch_marker.txt: unclassified source path" in error for error in errors))

    def test_invalid_and_duplicate_paths_fail_closed(self) -> None:
        errors = policy.validate_source_path_inventory(
            ["skeleton/kernel.py", "../escape.py", "skeleton/kernel.py", ""]
        )
        self.assertTrue(any("duplicate source path" in error for error in errors))
        self.assertTrue(any("repository-relative" in error for error in errors))
        self.assertTrue(any("non-empty" in error for error in errors))

    def test_non_list_inventory_fails_closed(self) -> None:
        self.assertEqual(
            policy.validate_source_path_inventory({"path": "skeleton/x.py"}),
            ["source path inventory must be a list of repository-relative paths"],
        )

    def test_valid_inventory_has_no_errors(self) -> None:
        paths = [path for path, _ in LIVE_EXAMPLES]
        self.assertEqual(policy.validate_source_path_inventory(paths), [])

    def test_live_examples_match_expected_classes(self) -> None:
        missing = [path for path, _ in LIVE_EXAMPLES if not (Path(__file__).resolve().parents[1] / path).exists()]
        self.assertEqual(missing, [])
        for path, expected in LIVE_EXAMPLES:
            self.assertEqual(policy.classify_path(path), expected, path)

    def test_live_tracked_tree_has_no_unknown_paths(self) -> None:
        paths = policy.tracked_source_paths()
        self.assertGreater(len(paths), 1000)
        errors = policy.validate_source_path_inventory(paths)
        self.assertEqual(errors, [])
        counts = policy.summarize(paths)
        self.assertEqual(counts["unknown"], 0)
        self.assertGreater(counts["canonical"], 0)
        self.assertGreater(counts["archive"], 0)
        self.assertGreater(counts["generated"], 0)
        self.assertGreater(counts["binary"], 0)
        self.assertGreater(counts["first-party"], 0)
        self.assertGreater(counts["fixture"], 0)
        self.assertEqual(sum(counts[klass] for klass in policy.CLASSES), len(paths))

    def test_main_accepts_the_live_repository(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(policy, "parse_args", return_value=mock.Mock(paths=None)):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = policy.main()
        self.assertEqual(status, 0)
        self.assertIn("source-path-inventory: OK", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_main_rejects_unknown_paths(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(policy, "parse_args", return_value=mock.Mock(paths=["mystery/x.py"])):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = policy.main()
        self.assertEqual(status, 1)
        self.assertIn("source-path-inventory: rejected", stderr.getvalue())
        self.assertIn("unclassified source path", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
