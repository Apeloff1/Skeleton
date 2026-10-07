from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.health import repository_health
from skeleton.repo_machine.impact import analyze_impact
from skeleton.repo_machine.manifest import (
    compare_manifest_states,
    load_manifest,
    manifest_envelope,
    save_manifest,
)
from skeleton.repo_machine.policy import evaluate_change_policy
from skeleton.repo_machine.query import RepositoryQuery


CONFIG = """
[repository]
schema_version = 1
name = "fixture"
default_owner = "supervisor"
max_files = 1000
max_file_bytes = 100000
max_context_bytes = 30000

[policy]
require_tests_for_code = true
require_readme_for_top_level_code = true
detect_dependency_cycles = true
detect_oversized_modules = true
oversized_python_lines = 100
oversized_javascript_lines = 100
oversized_generic_lines = 100

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
name = "github"
prefixes = [".github/"]
owner = "control"
criticality = "critical"

[[zone]]
name = "tests"
prefixes = ["tests/"]
owner = "quality"
criticality = "high"

[ignore]
prefixes = [".git/", "__pycache__/"]
suffixes = [".pyc"]
"""


def build_fixture(root: Path):
    (root / ".machine").mkdir(parents=True)
    (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
    (root / "alpha").mkdir()
    (root / "beta").mkdir()
    (root / "tests").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "alpha" / "__init__.py").write_text("", encoding="utf-8")
    (root / "beta" / "__init__.py").write_text("", encoding="utf-8")
    (root / "alpha" / "service.py").write_text(
        "import beta.api\n\ndef serve():\n    return 1\n",
        encoding="utf-8",
    )
    (root / "beta" / "api.py").write_text(
        "def call():\n    return 2\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_service.py").write_text(
        "def test_service():\n    assert True\n",
        encoding="utf-8",
    )
    (root / ".github" / "workflows" / "ci.yml").write_text(
        "name: CI\non: [push]\npermissions: {}\njobs: {}\n",
        encoding="utf-8",
    )
    return RepositoryModelBuilder(root).build()


class ImpactTests(unittest.TestCase):
    def test_impact_follows_reverse_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = build_fixture(Path(temp))
            report = analyze_impact(model, ["beta/api.py"])
            self.assertIn("beta", report.touched_zones)
            self.assertIn("alpha", report.directly_affected_zones)
            self.assertIn("alpha", report.transitively_affected_zones)
            self.assertIn("alpha", report.critical_zones)

    def test_workflow_change_is_high_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = build_fixture(Path(temp))
            report = analyze_impact(
                model,
                [".github/workflows/ci.yml"],
            )
            self.assertIn("github", report.touched_zones)
            self.assertGreaterEqual(report.risk_score, 20)
            self.assertTrue(any("Actions" in item for item in report.reasons))


class PolicyTests(unittest.TestCase):
    def test_python_change_requires_python_unit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = build_fixture(Path(temp))
            decision = evaluate_change_policy(model, ["alpha/service.py"])
            self.assertTrue(decision.allowed)
            self.assertIn("python-unit", decision.required_checks)
            self.assertIn("integration-smoke", decision.required_checks)

    def test_workflow_change_requires_security_and_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = build_fixture(Path(temp))
            decision = evaluate_change_policy(
                model,
                [".github/workflows/ci.yml"],
            )
            self.assertIn("workflow-input-security", decision.required_checks)
            self.assertIn("merge-readiness", decision.required_checks)

    def test_truncated_model_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".machine").mkdir()
            limited = CONFIG.replace("max_files = 1000", "max_files = 1")
            (root / ".machine" / "repository.toml").write_text(
                limited,
                encoding="utf-8",
            )
            (root / "alpha").mkdir()
            for i in range(5):
                (root / "alpha" / f"{i}.py").write_text("x=1\n", encoding="utf-8")
            model = RepositoryModelBuilder(root).build()
            self.assertTrue(model.truncated)
            decision = evaluate_change_policy(model, ["alpha/0.py"])
            self.assertFalse(decision.allowed)
            self.assertTrue(any("truncated" in item for item in decision.violations))


class ManifestTests(unittest.TestCase):
    def test_manifest_round_trip_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = build_fixture(root)
            manifest = root / "machine.json"
            save_manifest(model, manifest)
            loaded = load_manifest(manifest)
            self.assertEqual(loaded["fingerprint"], model.fingerprint)
            self.assertEqual(
                loaded["checksum"],
                manifest_envelope(model)["checksum"],
            )

    def test_manifest_detects_zone_change(self) -> None:
        before = {
            "subsystems": [{"name": "a", "file_count": 1}],
            "edges": [],
            "findings": [],
            "unclassified_count": 0,
        }
        after = {
            "subsystems": [
                {"name": "a", "file_count": 2},
                {"name": "b", "file_count": 1},
            ],
            "edges": [{"source": "a", "target": "b", "kind": "import"}],
            "findings": [{"code": "x"}],
            "unclassified_count": 1,
        }
        delta = compare_manifest_states(before, after)
        self.assertEqual(delta.added_zones, ("b",))
        self.assertEqual(delta.changed_zones, ("a",))
        self.assertEqual(delta.added_edges, ("a->b:import",))
        self.assertEqual(delta.finding_delta, 1)
        self.assertEqual(delta.unclassified_delta, 1)


class QueryAndHealthTests(unittest.TestCase):
    def test_query_filters_zone_and_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = build_fixture(Path(temp))
            query = RepositoryQuery(model)
            result = query.files(zones=["alpha"], kinds=["source"])
            self.assertTrue(result.files)
            self.assertTrue(all(item.zone == "alpha" for item in result.files))
            self.assertTrue(all(item.kind == "source" for item in result.files))

    def test_entrypoint_query_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = build_fixture(root)
            (root / "alpha" / "main.py").write_text("print('x')\n", encoding="utf-8")
            model = RepositoryModelBuilder(root).build()
            result = RepositoryQuery(model).entrypoints()
            self.assertIn("alpha/main.py", [item.path for item in result.files])

    def test_health_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            model = build_fixture(Path(temp))
            report = repository_health(model)
            self.assertGreaterEqual(report.score, 0)
            self.assertLessEqual(report.score, 100)
            self.assertIn(report.grade, {"A", "B", "C", "D", "F"})


if __name__ == "__main__":
    unittest.main()
