from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.context import _bounded, context_for_intent
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
        from skeleton.repo_machine import context as context_module

        with tempfile.TemporaryDirectory() as temp:
            model = fixture(Path(temp))
            full = context_for_intent(model, "overview")
            original_fits = context_module._fits
            checks = 0

            def finite_fits(payload, limit):
                nonlocal checks
                checks += 1
                self.assertLess(checks, 256, "context compaction made no finite progress")
                return original_fits(payload, limit)

            with patch.object(context_module, "_fits", side_effect=finite_fits):
                context = context_for_intent(model, "overview", byte_limit=4096)
            self.assertLessEqual(
                len(json.dumps(context, sort_keys=True, separators=(",", ":")).encode()),
                4096,
            )
            self.assertTrue(context["truncated_for_context"])
            self.assertEqual(context["fingerprint"], model.fingerprint)
            self.assertEqual(context["intent"], "overview")
            for key in ("health", "metrics", "coordination", "execution", "intelligence"):
                self.assertIn(key, context)
            for key in (
                "repository_fingerprint", "plan_fingerprint", "definition_fingerprint",
                "graph_fingerprint", "state", "ready_work", "blocked_work",
            ):
                self.assertEqual(context["execution"][key], full["execution"][key])
            for key in ("repository_fingerprint", "graph_fingerprint", "max_parallelism"):
                self.assertEqual(context["coordination"][key], full["coordination"][key])
            self.assertEqual(context, context_for_intent(model, "overview", byte_limit=4096))

    def test_oversized_required_execution_constraints_fail_closed(self) -> None:
        from skeleton.repo_machine.context import _bounded

        payload = {
            "intent": "overview", "fingerprint": "f" * 64,
            "execution": {"state": {"failed_work": ["constraint" * 1000]}},
        }
        with self.assertRaisesRegex(ValueError, "required repository context"):
            _bounded(payload, 4096)
        self.assertEqual(payload["execution"]["state"]["failed_work"], ["constraint" * 1000])


    def test_context_compaction_terminates_with_nonshrinking_metadata(self) -> None:
        oversized = {
            "intent": "overview",
            "fingerprint": "a" * 64,
            "health": {"large_evidence": "x" * 20000},
            "coordination": {"decisions": [], "safe_parallel_groups": []},
            "intelligence": {"decision_surface": [], "bridge_candidates": []},
        }
        context = _bounded(oversized, 4096)
        self.assertEqual(context["fingerprint"], oversized["fingerprint"])
        self.assertTrue(context["truncated_for_context"])
        self.assertLessEqual(
            len(json.dumps(context, sort_keys=True, separators=(",", ":")).encode()),
            4096,
        )
        self.assertEqual(context, _bounded(oversized, 4096))
        self.assertIn("health", oversized)  # Input is never mutated.

    def test_compaction_retains_required_execution_state_and_constraints(self) -> None:
        payload = {
            "intent": "repair",
            "fingerprint": "f" * 64,
            "health": {"evidence": "x" * 8000},
            "coordination": {"repository_fingerprint": "r" * 64, "graph_fingerprint": "g" * 64},
            "execution": {
                "state": {"failed_work": ["task-42"]},
                "constraints": {"source_digest": "a" * 64},
                "steps": [{"details": "y" * 3000} for _ in range(4)],
                "parallel_batches": [["b" * 2000] for _ in range(4)],
            },
        }
        result = _bounded(payload, 4096)
        self.assertLessEqual(len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()), 4096)
        self.assertEqual(result["fingerprint"], payload["fingerprint"])
        self.assertEqual(result["coordination"], payload["coordination"])
        self.assertEqual(result["execution"]["state"], payload["execution"]["state"])
        self.assertEqual(result["execution"]["constraints"], payload["execution"]["constraints"])
        self.assertTrue(result["truncated_for_context"])
        self.assertEqual(len(payload["execution"]["steps"]), 4)


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
