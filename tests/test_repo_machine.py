from __future__ import annotations

import json
from pathlib import Path
import tempfile
import textwrap
import unittest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.config import load_machine_config
from skeleton.repo_machine.planner import derive_work_candidates


CONFIG = """
[repository]
schema_version = 1
name = "fixture"
default_owner = "supervisor"
max_files = 100
max_file_bytes = 100000
max_context_bytes = 30000

[policy]
require_tests_for_code = true
require_readme_for_top_level_code = true
detect_dependency_cycles = true
detect_oversized_modules = true
oversized_python_lines = 8
oversized_javascript_lines = 8
oversized_generic_lines = 8

[[zone]]
name = "alpha"
prefixes = ["alpha/"]
owner = "alpha-team"
criticality = "high"

[[zone]]
name = "beta"
prefixes = ["beta/"]
owner = "beta-team"
criticality = "medium"

[[zone]]
name = "tests"
prefixes = ["tests/"]
owner = "quality"
criticality = "high"

[ignore]
prefixes = [".git/", "__pycache__/"]
suffixes = [".pyc"]
"""


class RepoMachineTests(unittest.TestCase):
    def fixture(self) -> tempfile.TemporaryDirectory[str]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / ".machine").mkdir()
        (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
        return temp

    def test_builds_zone_inventory_and_internal_edges(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            (root / "alpha").mkdir()
            (root / "beta").mkdir()
            (root / "alpha" / "__init__.py").write_text("", encoding="utf-8")
            (root / "beta" / "__init__.py").write_text("", encoding="utf-8")
            (root / "alpha" / "one.py").write_text("import beta.two\n\ndef run():\n    return 1\n", encoding="utf-8")
            (root / "beta" / "two.py").write_text("VALUE = 1\n", encoding="utf-8")

            model = RepositoryModelBuilder(root).build()

            self.assertEqual(
                {s.name for s in model.subsystems},
                {"alpha", "beta", "tests", "unclassified"},
            )
            self.assertTrue(any(e.source == "alpha" and e.target == "beta" for e in model.edges))
            self.assertGreaterEqual(model.metadata["file_count"], 4)
            self.assertEqual(len(model.fingerprint), 64)

    def test_detects_cross_zone_cycle(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            (root / "alpha").mkdir()
            (root / "beta").mkdir()
            (root / "alpha" / "a.py").write_text("import beta.b\n", encoding="utf-8")
            (root / "beta" / "b.py").write_text("import alpha.a\n", encoding="utf-8")

            model = RepositoryModelBuilder(root).build()

            self.assertIn(("alpha", "beta"), model.cycles)
            self.assertTrue(any(f.code == "topology.cycle" for f in model.findings))

    def test_detects_unclassified_and_oversized_source(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            (root / "misc").mkdir()
            (root / "alpha").mkdir()
            (root / "misc" / "x.py").write_text("x = 1\n", encoding="utf-8")
            (root / "alpha" / "big.py").write_text("\n".join(f"x{i} = {i}" for i in range(20)), encoding="utf-8")

            model = RepositoryModelBuilder(root).build()
            codes = {f.code for f in model.findings}

            self.assertIn("organization.unclassified", codes)
            self.assertIn("organization.oversized-module", codes)

    def test_missing_tests_becomes_ranked_work(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            (root / "alpha").mkdir()
            for index in range(4):
                (root / "alpha" / f"m{index}.py").write_text(f"VALUE = {index}\n", encoding="utf-8")

            model = RepositoryModelBuilder(root).build()
            work = derive_work_candidates(model)

            missing = [item for item in work if item.lane == "regression"]
            self.assertTrue(missing)
            self.assertEqual(missing[0].zone, "alpha")

    def test_machine_context_is_json_serializable_and_bounded_shape(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            (root / "alpha").mkdir()
            (root / "alpha" / "a.py").write_text("VALUE = 1\n", encoding="utf-8")

            model = RepositoryModelBuilder(root).build()
            context = model.machine_context()
            encoded = json.dumps(context)

            self.assertIn("fingerprint", context)
            self.assertIn("subsystems", context)
            self.assertIn("organization_findings", context)
            self.assertLess(len(encoded), 100000)

    def test_inventory_refuses_symlinked_files(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            (root / "alpha").mkdir()
            outside = root.parent / f"{root.name}-outside.py"
            outside.write_text("SECRET = 1\n", encoding="utf-8")
            link = root / "alpha" / "leak.py"
            try:
                link.symlink_to(outside)
            except OSError:
                outside.unlink(missing_ok=True)
                self.skipTest("symlinks unavailable")
            try:
                model = RepositoryModelBuilder(root).build()
            finally:
                outside.unlink(missing_ok=True)

            self.assertNotIn("alpha/leak.py", {item.path for item in model.files})
            self.assertTrue(any(
                finding.code == "scan.unreadable"
                and finding.path == "alpha/leak.py"
                for finding in model.findings
            ))

    def test_config_rejects_symlink_input(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            config_path = root / ".machine" / "repository.toml"
            outside = root.parent / f"{root.name}-config.toml"
            outside.write_text(CONFIG, encoding="utf-8")
            config_path.unlink()
            try:
                config_path.symlink_to(outside)
            except OSError:
                outside.unlink(missing_ok=True)
                self.skipTest("symlinks unavailable")
            try:
                with self.assertRaisesRegex(ValueError, "non-symlink"):
                    load_machine_config(root)
            finally:
                outside.unlink(missing_ok=True)

    def test_config_rejects_parent_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as external:
            root = Path(temp)
            external_machine = Path(external) / ".machine"
            external_machine.mkdir()
            (external_machine / "repository.toml").write_text(CONFIG, encoding="utf-8")
            try:
                (root / ".machine").symlink_to(external_machine, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "escapes repository root"):
                load_machine_config(root)

    def test_config_rejects_path_like_zone_name(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            config_path = root / ".machine" / "repository.toml"
            config = config_path.read_text(encoding="utf-8").replace(
                'name = "alpha"',
                'name = "alpha/../../escape"',
                1,
            )
            config_path.write_text(config, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "filename-safe"):
                load_machine_config(root)

    def test_config_rejects_duplicate_zone_names(self) -> None:
        with self.fixture() as temp:
            root = Path(temp)
            config = (root / ".machine" / "repository.toml").read_text(encoding="utf-8")
            config += textwrap.dedent("""
                [[zone]]
                name = "alpha"
                prefixes = ["other/"]
                owner = "other"
                criticality = "low"
            """)
            (root / ".machine" / "repository.toml").write_text(config, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_machine_config(root)


if __name__ == "__main__":
    unittest.main()
