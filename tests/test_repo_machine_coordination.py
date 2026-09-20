from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.context_budget import allocate_context
from skeleton.repo_machine.coordinator import build_coordinator_snapshot
from skeleton.repo_machine.evolution import evaluate_evolution
from skeleton.repo_machine.layout import analyze_layout
from skeleton.repo_machine.naming import analyze_naming
from skeleton.repo_machine.refactor import plan_refactors


CONFIG = """
[repository]
schema_version = 1
name = "coord-fixture"
default_owner = "supervisor"
max_files = 5000
max_file_bytes = 500000
max_context_bytes = 30000

[policy]
require_tests_for_code = true
require_readme_for_top_level_code = true
detect_dependency_cycles = true
detect_oversized_modules = true
oversized_python_lines = 50
oversized_javascript_lines = 50
oversized_generic_lines = 50

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
name = "docs"
prefixes = ["docs/"]
owner = "docs-owner"
criticality = "medium"

[ignore]
prefixes = [".git/", "__pycache__/"]
suffixes = [".pyc"]
"""


def fixture(root: Path):
    (root / ".machine").mkdir()
    (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
    for name in ("app", "lib", "tests", "docs"):
        (root / name).mkdir()
    (root / "app" / "service.py").write_text(
        "import lib.api\n" + "\n".join(
            f"def operation_{i}(): return {i}" for i in range(70)
        ) + "\n",
        encoding="utf-8",
    )
    (root / "app" / "utils.py").write_text("def helper(): return 1\n", encoding="utf-8")
    (root / "lib" / "api.py").write_text("def request(): return 1\n", encoding="utf-8")
    (root / "tests" / "test_service.py").write_text(
        "import app.service\n\ndef test_service(): assert True\n",
        encoding="utf-8",
    )
    (root / "docs" / "app.md").write_text("# App\n", encoding="utf-8")
    builder = RepositoryModelBuilder(root)
    return builder, builder.build()


class RefactorCoordinatorTests(unittest.TestCase):
    def test_hot_module_gets_refactor_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            plans = plan_refactors(model, minimum_hotspot_score=20)
            self.assertTrue(any(item.source_path == "app/service.py" for item in plans))

    def test_coordinator_returns_bounded_machine_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder, model = fixture(Path(temp))
            snapshot = build_coordinator_snapshot(model, builder.config)
            payload = snapshot.as_dict()
            self.assertEqual(payload["repository_fingerprint"], model.fingerprint)
            self.assertLessEqual(len(payload["queue_ready"]), 6)
            self.assertIn("layout", payload)
            self.assertIn("context_allocations", payload)


class ContextNamingLayoutTests(unittest.TestCase):
    def test_context_allocations_cover_every_zone(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            allocations = allocate_context(model, total_bytes=40000)
            self.assertEqual(
                {item.zone for item in allocations},
                {item.name for item in model.subsystems},
            )
            self.assertTrue(all(item.byte_budget >= 2000 for item in allocations))

    def test_ambiguous_utils_name_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            findings = analyze_naming(model)
            self.assertTrue(any(
                item.path == "app/utils.py"
                and item.code == "naming.ambiguous-file"
                for item in findings
            ))

    def test_layout_profile_counts_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            profile = analyze_layout(model)
            self.assertGreaterEqual(profile.root_directory_count, 4)
            self.assertTrue(any(item.name == "app" for item in profile.roots))


class EvolutionTests(unittest.TestCase):
    def test_reducing_unclassified_surface_improves_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            builder, before = fixture(root)
            (root / "misc.py").write_text("x=1\n", encoding="utf-8")
            worse = RepositoryModelBuilder(root).build()
            (root / "misc.py").unlink()
            after = RepositoryModelBuilder(root).build()

            regression = evaluate_evolution(before, worse)
            improvement = evaluate_evolution(worse, after)
            self.assertLessEqual(regression.score, improvement.score)
            self.assertLess(improvement.unclassified_delta, 0)


if __name__ == "__main__":
    unittest.main()
