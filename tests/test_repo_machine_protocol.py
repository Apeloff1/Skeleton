from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.protocol import MachineRequest, handle_request
from skeleton.repo_machine.selfcheck import run_selfcheck, selfcheck_ok


CONFIG = """
[repository]
schema_version = 1
name = "protocol-fixture"
default_owner = "supervisor"
max_files = 5000
max_file_bytes = 500000
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
name = "repo-machine"
prefixes = [".machine/", "skeleton/repo_machine/"]
owner = "machine-architecture"
criticality = "critical"

[[zone]]
name = "app"
prefixes = ["app/"]
owner = "app-owner"
criticality = "high"

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
    (root / "skeleton" / "repo_machine").mkdir(parents=True)
    (root / "skeleton" / "repo_machine" / "core.py").write_text(
        "def index(): return 1\n",
        encoding="utf-8",
    )
    (root / "app").mkdir()
    (root / "tests").mkdir()
    (root / "app" / "service.py").write_text(
        "def service(): return 1\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_service.py").write_text(
        "def test_service(): assert True\n",
        encoding="utf-8",
    )
    builder = RepositoryModelBuilder(root)
    return builder, builder.build()


class ProtocolTests(unittest.TestCase):
    def test_search_request_is_typed_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder, model = fixture(Path(temp))
            response = handle_request(
                model,
                builder.config,
                MachineRequest("search", query="service"),
            )
            self.assertEqual(response.operation, "search")
            self.assertTrue(response.payload["hits"])

    def test_context_request_uses_allowed_intent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder, model = fixture(Path(temp))
            response = handle_request(
                model,
                builder.config,
                MachineRequest("context", intent="architecture"),
            )
            self.assertEqual(response.payload["intent"], "architecture")

    def test_protocol_rejects_unknown_operation(self) -> None:
        with self.assertRaises(ValueError):
            MachineRequest("shell", query="rm -rf .")


class SelfCheckTests(unittest.TestCase):
    def test_first_class_machine_zone_passes_zone_selfcheck(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder, model = fixture(Path(temp))
            findings = run_selfcheck(model, builder.config)
            codes = {item.code for item in findings}
            self.assertNotIn("selfcheck.machine-zone-missing", codes)
            self.assertNotIn("selfcheck.machine-zone-criticality", codes)

    def test_selfcheck_ok_has_no_high_machine_integrity_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder, model = fixture(Path(temp))
            self.assertTrue(selfcheck_ok(model, builder.config))


if __name__ == "__main__":
    unittest.main()
