from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.budgets import derive_zone_budgets
from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.governance import validate_governance
from skeleton.repo_machine.hotspots import structural_hotspots
from skeleton.repo_machine.model_diff import compare_models
from skeleton.repo_machine.relations import build_relations, reachable_files
from skeleton.repo_machine.reorganize import propose_reorganization
from skeleton.repo_machine.retrieval import RepositoryRetrievalIndex
from skeleton.repo_machine.workspace import generate_workspace


CONFIG = """
[repository]
schema_version = 1
name = "sota-fixture"
default_owner = "supervisor"
max_files = 5000
max_file_bytes = 500000
max_context_bytes = 30000

[policy]
require_tests_for_code = true
require_readme_for_top_level_code = true
detect_dependency_cycles = true
detect_oversized_modules = true
oversized_python_lines = 60
oversized_javascript_lines = 60
oversized_generic_lines = 60

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

[ignore]
prefixes = [".git/", "__pycache__/", ".machine/generated/"]
suffixes = [".pyc"]
"""


def fixture(root: Path):
    (root / ".machine").mkdir()
    (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
    (root / "app").mkdir()
    (root / "lib").mkdir()
    (root / "tests").mkdir()
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "main.py").write_text(
        "import lib.api\n" + "\n".join(
            [f"def f{i}(): return {i}" for i in range(70)]
        ) + "\n",
        encoding="utf-8",
    )
    (root / "lib" / "api.py").write_text(
        "def request(): return 1\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_main.py").write_text(
        "def test_main(): assert True\n",
        encoding="utf-8",
    )
    return RepositoryModelBuilder(root).build()


class RetrievalTests(unittest.TestCase):
    def test_search_prefers_exact_basename(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            index = RepositoryRetrievalIndex(model)
            hits = index.search("main")
            self.assertTrue(hits)
            self.assertEqual(hits[0].path, "app/main.py")

    def test_zone_filter_is_respected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            hits = RepositoryRetrievalIndex(model).search(
                "api",
                zones=["lib"],
            )
            self.assertTrue(hits)
            self.assertTrue(all(item.zone == "lib" for item in hits))


class HotspotBudgetTests(unittest.TestCase):
    def test_large_symbol_dense_module_is_hotspot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            paths = {
                item.path
                for item in structural_hotspots(model)
            }
            self.assertIn("app/main.py", paths)

    def test_high_criticality_zone_has_conservative_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            budgets = {
                item.zone: item
                for item in derive_zone_budgets(model)
            }
            self.assertLessEqual(budgets["app"].max_parallel_objectives, 1)
            self.assertLessEqual(budgets["app"].max_changed_files, 12)


class RelationTests(unittest.TestCase):
    def test_internal_import_relation_is_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            relations = build_relations(model)
            self.assertTrue(any(
                item.source_path == "app/main.py"
                and item.target_path == "lib/api.py"
                for item in relations
            ))

    def test_reachability_follows_internal_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            reached = reachable_files(model, "app/main.py")
            self.assertIn("lib/api.py", reached)


class GovernanceReorganizationTests(unittest.TestCase):
    def test_unclassified_path_gets_reorganization_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = fixture(root)
            (root / "misc").mkdir()
            (root / "misc" / "thing.py").write_text("x=1\n", encoding="utf-8")
            builder = RepositoryModelBuilder(root)
            model = builder.build()
            proposals = propose_reorganization(model, builder.config)
            self.assertTrue(any(
                item.category == "classification"
                for item in proposals
            ))

    def test_governance_report_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = fixture(root)
            builder = RepositoryModelBuilder(root)
            first = validate_governance(model, builder.config)
            second = validate_governance(model, builder.config)
            self.assertEqual(first, second)


class ModelDiffWorkspaceTests(unittest.TestCase):
    def test_model_diff_tracks_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            before = fixture(root)
            (root / "lib" / "api.py").write_text(
                "def request(): return 2\n",
                encoding="utf-8",
            )
            after = RepositoryModelBuilder(root).build()
            delta = compare_models(before, after)
            self.assertIn("lib/api.py", delta.changed_files)

    def test_workspace_pack_contains_machine_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = fixture(root)
            builder = RepositoryModelBuilder(root)
            destination = root / "machine-pack"
            files = generate_workspace(
                model,
                builder.config,
                destination,
            )
            self.assertIn("repository-manifest.json", files)
            self.assertIn("health.json", files)
            self.assertIn("steward-plan.json", files)
            self.assertTrue((destination / "index.json").exists())


if __name__ == "__main__":
    unittest.main()
