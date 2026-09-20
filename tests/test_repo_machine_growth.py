from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.context import context_for_intent
from skeleton.repo_machine.growth import growth_recommendations
from skeleton.repo_machine.metrics import structural_metrics
from skeleton.repo_machine.ownership import analyze_ownership
from skeleton.repo_machine.workgraph import build_work_graph


CONFIG = """
[repository]
schema_version = 1
name = "growth-fixture"
default_owner = "supervisor"
max_files = 5000
max_file_bytes = 100000
max_context_bytes = 30000

[policy]
require_tests_for_code = true
require_readme_for_top_level_code = true
detect_dependency_cycles = true
detect_oversized_modules = true
oversized_python_lines = 500
oversized_javascript_lines = 500
oversized_generic_lines = 500

[[zone]]
name = "alpha"
prefixes = ["alpha/"]
owner = "alpha-owner"
criticality = "high"

[[zone]]
name = "beta"
prefixes = ["beta/"]
owner = "beta-owner"
criticality = "medium"

[[zone]]
name = "tests"
prefixes = ["tests/"]
owner = "quality-owner"
criticality = "high"

[ignore]
prefixes = [".git/", "__pycache__/"]
suffixes = [".pyc"]
"""


def fixture(root: Path):
    (root / ".machine").mkdir()
    (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
    (root / "alpha").mkdir()
    (root / "beta").mkdir()
    (root / "tests").mkdir()
    for index in range(6):
        (root / "alpha" / f"a{index}.py").write_text(
            "import beta.api\n" + "\n".join(f"v{i}={i}" for i in range(20)),
            encoding="utf-8",
        )
    (root / "beta" / "api.py").write_text("VALUE=1\n", encoding="utf-8")
    (root / "tests" / "test_alpha.py").write_text("def test_x(): assert True\n", encoding="utf-8")
    return RepositoryModelBuilder(root).build()


class MetricsOwnershipTests(unittest.TestCase):
    def test_metrics_cover_all_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            metrics = structural_metrics(model)
            self.assertEqual(metrics.total_files, len(model.files))
            self.assertGreater(metrics.total_lines, 0)
            self.assertGreaterEqual(metrics.largest_zone_line_share, 0.0)
            self.assertLessEqual(metrics.largest_zone_line_share, 1.0)

    def test_ownership_report_tracks_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = fixture(root)
            config = RepositoryModelBuilder(root).config
            report = analyze_ownership(model, config)
            self.assertIn("alpha-owner", report.owners)
            self.assertGreater(report.coverage_ratio, 0.5)


class ContextWorkGraphTests(unittest.TestCase):
    def test_architecture_context_contains_topology(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            context = context_for_intent(model, "architecture")
            self.assertEqual(context["intent"], "architecture")
            self.assertIn("topology", context)
            self.assertIn("metrics", context)

    def test_work_graph_prevents_same_lane_zone_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            graph = build_work_graph(model)
            ready = graph.ready(limit=20)
            conflicts: set[str] = set()
            for node in ready:
                self.assertFalse(conflicts.intersection(node.conflict_keys))
                conflicts.update(node.conflict_keys)

    def test_truncated_context_compacts_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            context = context_for_intent(model, "overview", byte_limit=4096)
            self.assertIn("fingerprint", context)


class GrowthTests(unittest.TestCase):
    def test_growth_recommendations_are_priority_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            items = growth_recommendations(model)
            priorities = [item.priority for item in items]
            self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_cycle_recommendation_is_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = fixture(root)
            (root / "beta" / "api.py").write_text("import alpha.a0\n", encoding="utf-8")
            model = RepositoryModelBuilder(root).build()
            codes = {item.code for item in growth_recommendations(model)}
            self.assertIn("growth.break-cycles", codes)


if __name__ == "__main__":
    unittest.main()
