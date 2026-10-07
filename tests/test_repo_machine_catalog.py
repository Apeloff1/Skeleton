from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.catalog import build_catalog
from skeleton.repo_machine.contracts import derive_contracts
from skeleton.repo_machine.navigation import NavigationIndex
from skeleton.repo_machine.shards import build_context_shards, shard_index
from skeleton.repo_machine.steward import select_steward_plan


CONFIG = """
[repository]
schema_version = 1
name = "catalog-fixture"
default_owner = "supervisor"
max_files = 1000
max_file_bytes = 100000
max_context_bytes = 30000

[policy]
require_tests_for_code = true
require_readme_for_top_level_code = true
detect_dependency_cycles = true
detect_oversized_modules = true
oversized_python_lines = 1000
oversized_javascript_lines = 1000
oversized_generic_lines = 1000

[[zone]]
name = "app"
prefixes = ["app/"]
owner = "app-owner"
criticality = "high"

[[zone]]
name = "lib"
prefixes = ["lib/"]
owner = "lib-owner"
criticality = "medium"

[[zone]]
name = "tests"
prefixes = ["tests/"]
owner = "quality-owner"
criticality = "high"

[[zone]]
name = "github"
prefixes = [".github/"]
owner = "control-owner"
criticality = "critical"

[ignore]
prefixes = [".git/", "__pycache__/"]
suffixes = [".pyc"]
"""


def model_fixture(root: Path):
    (root / ".machine").mkdir()
    (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
    (root / "app").mkdir()
    (root / "lib").mkdir()
    (root / "tests").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "app" / "main.py").write_text(
        "import lib.api\n\ndef one(): pass\ndef two(): pass\ndef three(): pass\ndef four(): pass\ndef five(): pass\n",
        encoding="utf-8",
    )
    (root / "lib" / "api.py").write_text("def call(): return 1\n", encoding="utf-8")
    (root / "tests" / "test_main.py").write_text("def test_main(): assert True\n", encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text("name: CI\non: [push]\npermissions: {}\njobs: {}\n", encoding="utf-8")
    return RepositoryModelBuilder(root).build()


class CatalogContractTests(unittest.TestCase):
    def test_catalog_contains_entrypoint_workflow_and_module(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = model_fixture(Path(temp))
            catalog = build_catalog(model)
            kinds = {item.kind for item in catalog.capabilities}
            self.assertIn("entrypoint", kinds)
            self.assertIn("workflow", kinds)
            self.assertIn("module", kinds)

    def test_contracts_expose_dependency_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = model_fixture(Path(temp))
            contracts = {item.zone: item for item in derive_contracts(model)}
            self.assertIn("lib", contracts["app"].allowed_dependencies)
            self.assertEqual(contracts["app"].owner, "app-owner")


class NavigationShardTests(unittest.TestCase):
    def test_navigation_directory_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = model_fixture(Path(temp))
            nav = NavigationIndex(model)
            app = nav.directory("app")
            self.assertGreaterEqual(app.files, 1)
            self.assertIn("app", app.zones)
            nearest = nav.nearest(zone="app", name_contains="main")
            self.assertEqual(nearest[0].path, "app/main.py")

    def test_context_shards_are_stable_and_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = model_fixture(Path(temp))
            shards = build_context_shards(model)
            index = shard_index(model)
            self.assertEqual(len(shards), len(model.subsystems))
            self.assertEqual(index["repository_fingerprint"], model.fingerprint)
            self.assertTrue(all(len(shard.digest) == 64 for shard in shards))


class StewardTests(unittest.TestCase):
    def test_steward_plan_is_bounded_and_conflict_aware(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = model_fixture(root)
            (root / "misc.py").write_text("x=1\n", encoding="utf-8")
            model = RepositoryModelBuilder(root).build()
            plan = select_steward_plan(model, max_objectives=3)
            self.assertLessEqual(len(plan.objectives), 3)
            conflicts: set[str] = set()
            for objective in plan.objectives:
                self.assertFalse(conflicts.intersection(objective.conflict_keys))
                conflicts.update(objective.conflict_keys)


if __name__ == "__main__":
    unittest.main()
