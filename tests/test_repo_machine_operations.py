from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.docs_map import documentation_coverage, undocumented_code_zones
from skeleton.repo_machine.intent import ChangeIntent, assess_change_intent, intents_conflict
from skeleton.repo_machine.leases import LeaseRegistry
from skeleton.repo_machine.ledger import ArchitectureLedger
from skeleton.repo_machine.package_graph import discover_package_units
from skeleton.repo_machine.test_affinity import build_test_affinity, uncovered_sources
from skeleton.repo_machine.work_queue import MachineWorkQueue


CONFIG = """
[repository]
schema_version = 1
name = "operations-fixture"
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
name = "docs"
prefixes = ["docs/", "README"]
owner = "docs-owner"
criticality = "medium"

[ignore]
prefixes = [".git/", "__pycache__/"]
suffixes = [".pyc"]
"""


def fixture(root: Path):
    (root / ".machine").mkdir()
    (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
    (root / "app").mkdir()
    (root / "lib").mkdir()
    (root / "tests").mkdir()
    (root / "docs").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (root / "app" / "service.py").write_text(
        "import lib.api\n\ndef serve(): return 1\n",
        encoding="utf-8",
    )
    (root / "app" / "orphan.py").write_text(
        "def orphan(): return 2\n",
        encoding="utf-8",
    )
    (root / "lib" / "api.py").write_text(
        "def request(): return 1\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_service.py").write_text(
        "import app.service\n\ndef test_service(): assert True\n",
        encoding="utf-8",
    )
    (root / "docs" / "app.md").write_text("# App\n", encoding="utf-8")
    builder = RepositoryModelBuilder(root)
    return builder, builder.build()


class IntentTests(unittest.TestCase):
    def test_intent_assessment_requires_python_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            intent = ChangeIntent(
                identity="repair.app.service",
                lane="repair",
                objective="repair service behavior",
                paths=("app/service.py",),
            )
            assessment = assess_change_intent(model, intent, estimated_changed_lines=100)
            self.assertTrue(assessment.allowed)
            self.assertIn("python-unit", assessment.required_checks)

    def test_same_zone_intents_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            left = ChangeIntent("repair.app.a", "repair", "a", ("app/service.py",))
            right = ChangeIntent("repair.app.b", "repair", "b", ("app/orphan.py",))
            self.assertTrue(intents_conflict(left, right, model))


class AffinityDocumentationTests(unittest.TestCase):
    def test_source_test_affinity_finds_matching_test(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            affinity = build_test_affinity(model)
            matches = affinity["app/service.py"]
            self.assertTrue(matches)
            self.assertEqual(matches[0].test_path, "tests/test_service.py")

    def test_orphan_source_is_uncovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            self.assertIn("app/orphan.py", uncovered_sources(model))

    def test_documentation_coverage_links_app_doc(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            coverage = {item.zone: item for item in documentation_coverage(model)}
            self.assertTrue(coverage["app"].covered)
            self.assertNotIn("app", undocumented_code_zones(model))


class LeaseLedgerTests(unittest.TestCase):
    def test_lease_registry_rejects_conflicting_work(self) -> None:
        registry = LeaseRegistry()
        lease = registry.acquire(
            objective_id="a",
            holder="worker-1",
            conflict_keys=("zone:app",),
            repository_fingerprint="f" * 64,
            now=100,
            ttl_seconds=100,
        )
        self.assertFalse(registry.can_acquire(("zone:app",), 150))
        self.assertTrue(registry.release(lease.lease_id))
        self.assertTrue(registry.can_acquire(("zone:app",), 150))

    def test_lease_registry_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "leases.json"
            registry = LeaseRegistry()
            registry.acquire(
                objective_id="a",
                holder="worker-1",
                conflict_keys=("zone:app",),
                repository_fingerprint="f" * 64,
                now=100,
                ttl_seconds=100,
            )
            registry.save(path)
            loaded = LeaseRegistry.load(path)
            self.assertEqual(registry.leases, loaded.leases)

    def test_architecture_ledger_hash_chain(self) -> None:
        ledger = ArchitectureLedger()
        first = ledger.append(
            timestamp=100,
            kind="architecture",
            repository_fingerprint="a" * 64,
            subject="app",
            summary="establish boundary",
        )
        second = ledger.append(
            timestamp=200,
            kind="validation",
            repository_fingerprint="b" * 64,
            subject="app",
            summary="boundary validated",
            evidence=("ci:1",),
        )
        self.assertEqual(second.previous_digest, first.digest)
        ledger.validate()


class QueuePackageTests(unittest.TestCase):
    def test_work_queue_refresh_is_fingerprint_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder, model = fixture(Path(temp))
            queue = MachineWorkQueue()
            queue.refresh(model, builder.config)
            ready = queue.ready(limit=4)
            self.assertLessEqual(len(ready), 4)
            self.assertTrue(all(item.repository_fingerprint == model.fingerprint for item in ready))

    def test_package_unit_discovers_root_python_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, model = fixture(Path(temp))
            units = discover_package_units(model)
            self.assertTrue(any(item.ecosystem == "python" for item in units))


if __name__ == "__main__":
    unittest.main()
