from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_developer_setup_inventory.py"
SPEC = importlib.util.spec_from_file_location("check_developer_setup_inventory", SCRIPT)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)

REPO_ROOT = Path(__file__).resolve().parents[1]

CLOSED_PYPROJECT = """
[project]
name = "fixture"
requires-python = ">=3.11"
optional-dependencies = { dev = ["pytest>=7.0.0", "ruff>=0.9,<0.17", "mypy>=1.0.0", "black>=23.0.0"] }

[tool.uv]
required-version = "==0.12.15"
"""

CLOSED_README = """# Fixture

Requires Python 3.11, Node 24, uv 0.12.15, yarn, pytest, ruff, mypy, and black.
"""

CLOSED_AGENTS = """# Agent setup

Use Python 3.11, Node 24, uv==0.12.15, and yarn.
"""

CLOSED_REQUIREMENTS_DEV = """\
-r requirements.txt
pytest>=7.0.0
ruff>=0.9,<0.17
mypy>=1.0.0
black>=23.0.0
"""

CLOSED_REQUIREMENTS = """\
fastapi>=0.141.1
"""

CLOSED_WORKFLOW = """\
name: CI
on: push
env:
  PYTHON_VERSION: "3.11.16"
  NODE_VERSION: "24.20.0"
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v10
      - uses: actions/setup-python@v5
        with:
          python-version: "${{ env.PYTHON_VERSION }}"
      - uses: actions/setup-node@v4
        with:
          node-version: "${{ env.NODE_VERSION }}"
          cache: yarn
"""

CLOSED_PACKAGE_JSON = {
    "name": "frontend",
    "engines": {"node": ">=24"},
    "packageManager": "yarn@1.22.22+sha512.deadbeef",
}


def _write(root: Path, relative: str, content: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def _closed_fixture(root: Path) -> None:
    _write(root, "README.md", CLOSED_README)
    _write(root, "AGENTS.md", CLOSED_AGENTS)
    _write(root, "pyproject.toml", CLOSED_PYPROJECT)
    _write(root, "requirements.txt", CLOSED_REQUIREMENTS)
    _write(root, "requirements-dev.txt", CLOSED_REQUIREMENTS_DEV)
    _write(root, ".github/workflows/ci.yml", CLOSED_WORKFLOW)
    _write(root, "frontend/package.json", json.dumps(CLOSED_PACKAGE_JSON))


class DeveloperSetupInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def scan(self, root: Path | None = None) -> object:
        return inventory.scan_developer_setup(root or self.root)

    def by_name(self, scanned: object) -> dict[str, object]:
        return {item.name: item for item in scanned.items}

    def test_task_identity_is_stable(self) -> None:
        self.assertEqual(inventory.TASK_KEY, "reserve-S101-developer-setup-audit")
        self.assertEqual(inventory.CONFLICT_DOMAIN, "dx.readonly.setup_audit")
        self.assertEqual(
            inventory.CLOSED_CLASSES,
            {"documented", "assumed", "drifting", "unknown"},
        )

    def test_closed_fixture_is_documented(self) -> None:
        _closed_fixture(self.root)
        scanned = self.scan()
        self.assertEqual(scanned.errors, ())
        self.assertTrue(scanned.is_closed())
        names = {item.name for item in scanned.items}
        self.assertTrue(
            {"python", "node", "uv", "yarn", "pytest", "ruff", "mypy", "black"} <= names
        )
        for item in scanned.items:
            self.assertEqual(item.classification, "documented")
            self.assertIn(item.classification, inventory.CLOSED_CLASSES)

    def test_assumed_when_docs_omit_node(self) -> None:
        _closed_fixture(self.root)
        _write(
            self.root,
            "README.md",
            "# Fixture\n\nRequires Python 3.11, uv 0.12.15, yarn, pytest, ruff, mypy, and black.\n",
        )
        _write(self.root, "AGENTS.md", "# Agent setup\n\nUse Python 3.11, uv==0.12.15, and yarn.\n")
        scanned = self.scan()
        node = self.by_name(scanned)["node"]
        self.assertEqual(node.classification, "assumed")
        self.assertIn("undocumented", node.note)
        self.assertFalse(scanned.is_closed())

    def test_docs_only_npm_is_drifting(self) -> None:
        _closed_fixture(self.root)
        _write(
            self.root,
            "README.md",
            CLOSED_README + "\nInstall with npm install.\n",
        )
        scanned = self.scan()
        npm = self.by_name(scanned)["npm"]
        self.assertEqual(npm.classification, "drifting")
        self.assertIn("missing from machine-readable setup", npm.note)
        self.assertFalse(scanned.is_closed())

    def test_unquoted_workflow_env_expression_resolves(self) -> None:
        _closed_fixture(self.root)
        _write(
            self.root,
            ".github/workflows/ci.yml",
            """\
name: CI
on: push
env:
  PYTHON_VERSION: "3.11.16"
  NODE_VERSION: "24.20.0"
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: astral-sh/setup-uv@v10
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: yarn
""",
        )
        scanned = self.scan()
        python = self.by_name(scanned)["python"]
        node = self.by_name(scanned)["node"]
        self.assertNotIn("${{", python.versions)
        self.assertIn("3.11.16", python.versions)
        self.assertIn("24.20.0", node.versions)
        self.assertEqual(python.classification, "documented")

    def test_version_conflict_is_drifting(self) -> None:
        _closed_fixture(self.root)
        _write(
            self.root,
            "README.md",
            "# Fixture\n\nRequires Python 3.12, Node 24, uv 0.12.15, yarn, pytest, ruff, mypy, and black.\n",
        )
        scanned = self.scan()
        python = self.by_name(scanned)["python"]
        self.assertEqual(python.classification, "drifting")
        self.assertIn("disagree", python.note)
        self.assertFalse(scanned.is_closed())

    def test_unknown_setup_action_is_unknown(self) -> None:
        _closed_fixture(self.root)
        _write(
            self.root,
            ".github/workflows/ci.yml",
            CLOSED_WORKFLOW
            + "\n      - uses: actions/setup-java@v4\n        with:\n          java-version: '21'\n",
        )
        scanned = self.scan()
        java = self.by_name(scanned)["actions/setup-java"]
        self.assertEqual(java.classification, "unknown")
        self.assertIn("closed tool catalog", java.note)
        self.assertFalse(scanned.is_closed())

    def test_unknown_package_manager_is_unknown(self) -> None:
        _closed_fixture(self.root)
        payload = dict(CLOSED_PACKAGE_JSON)
        payload["packageManager"] = "pnpm@9.0.0"
        _write(self.root, "frontend/package.json", json.dumps(payload))
        scanned = self.scan()
        pnpm = self.by_name(scanned)["pnpm"]
        self.assertEqual(pnpm.classification, "unknown")
        self.assertFalse(scanned.is_closed())

    def test_does_not_invent_uncatalogued_optional_deps(self) -> None:
        _closed_fixture(self.root)
        _write(
            self.root,
            "pyproject.toml",
            """
[project]
name = "fixture"
requires-python = ">=3.11"
optional-dependencies = { dev = ["pytest>=7.0.0", "pre-commit>=3.6.0", "httpx>=0.26.0"] }

[tool.uv]
required-version = "==0.12.15"
""",
        )
        scanned = self.scan()
        names = {item.name for item in scanned.items}
        self.assertIn("pytest", names)
        self.assertNotIn("pre-commit", names)
        self.assertNotIn("httpx", names)
        self.assertNotIn("fastapi", names)

    def test_missing_required_docs_fail_closed(self) -> None:
        _write(self.root, "pyproject.toml", CLOSED_PYPROJECT)
        _write(self.root, ".github/workflows/ci.yml", CLOSED_WORKFLOW)
        scanned = self.scan()
        self.assertTrue(any("README.md" in error for error in scanned.errors))
        self.assertTrue(any("AGENTS.md" in error for error in scanned.errors))
        self.assertFalse(scanned.is_closed())
        with mock.patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(inventory.main(["--root", str(self.root)]), 1)

    def test_unreadable_docs_fail_closed(self) -> None:
        _closed_fixture(self.root)
        _write(self.root, "AGENTS.md", b"\xff\xfe not utf-8 \x80")
        scanned = self.scan()
        self.assertTrue(any("unreadable" in error and "AGENTS.md" in error for error in scanned.errors))
        self.assertFalse(scanned.is_closed())

    def test_invalid_pyproject_fails_closed(self) -> None:
        _closed_fixture(self.root)
        _write(self.root, "pyproject.toml", "[project\nname = ")
        scanned = self.scan()
        self.assertTrue(any("invalid TOML" in error for error in scanned.errors))
        self.assertFalse(scanned.is_closed())

    def test_invalid_package_json_fails_closed(self) -> None:
        _closed_fixture(self.root)
        _write(self.root, "frontend/package.json", "{not json")
        scanned = self.scan()
        self.assertTrue(any("invalid JSON" in error for error in scanned.errors))
        self.assertFalse(scanned.is_closed())

    def test_requirements_include_escape_fails_closed(self) -> None:
        _closed_fixture(self.root)
        _write(self.root, "requirements-dev.txt", "-r /etc/passwd\npytest>=7.0.0\n")
        scanned = self.scan()
        self.assertTrue(any("escapes the repository root" in error for error in scanned.errors))
        self.assertFalse(scanned.is_closed())

    def test_archived_branch_snapshots_are_ignored(self) -> None:
        _closed_fixture(self.root)
        _write(
            self.root,
            "satellites/branch-snapshots/old/frontend/package.json",
            json.dumps(
                {
                    "name": "archived",
                    "engines": {"node": "10.0.0"},
                    "packageManager": "pnpm@1.0.0",
                }
            ),
        )
        scanned = self.scan()
        node = self.by_name(scanned)["node"]
        self.assertNotIn("10.0.0", node.versions)
        self.assertNotIn("pnpm", self.by_name(scanned))

    def test_docker_setup_buildx_is_not_invented_as_a_host_tool(self) -> None:
        _closed_fixture(self.root)
        _write(
            self.root,
            ".github/workflows/ci.yml",
            CLOSED_WORKFLOW + "\n      - uses: docker/setup-buildx-action@v4\n",
        )
        scanned = self.scan()
        names = {item.name for item in scanned.items}
        self.assertNotIn("docker", names)
        self.assertNotIn("docker/setup-buildx-action", names)
        self.assertTrue(scanned.is_closed())

    def test_compatible_python_pin_and_floor_are_documented(self) -> None:
        _closed_fixture(self.root)
        scanned = self.scan()
        python = self.by_name(scanned)["python"]
        self.assertEqual(python.classification, "documented")
        self.assertTrue(inventory.versions_compatible([">=3.11", "3.11.16", "3.11"]))

    def test_incompatible_pins_are_not_compatible(self) -> None:
        self.assertFalse(inventory.versions_compatible(["3.11.16", "3.12"]))
        self.assertFalse(inventory.versions_compatible([">=3.11", "3.10"]))
        self.assertFalse(inventory.versions_compatible(["3.11.11", "3.11.16"]))

    def test_current_repo_scan_is_deterministic(self) -> None:
        first = inventory.scan_developer_setup(REPO_ROOT)
        second = inventory.scan_developer_setup(REPO_ROOT)
        self.assertEqual(first, second)
        self.assertEqual(first.task_key, inventory.TASK_KEY)
        self.assertEqual(first.conflict_domain, inventory.CONFLICT_DOMAIN)
        self.assertTrue(any("AGENTS.md" in error for error in first.errors))
        names = [item.name for item in first.items]
        self.assertEqual(names, sorted(names))
        for item in first.items:
            self.assertIn(item.classification, inventory.CLOSED_CLASSES)
        by_name = self.by_name(first)
        self.assertEqual(by_name["python"].classification, "drifting")
        self.assertIn("3.11.11", by_name["python"].versions)
        self.assertIn("3.11.16", by_name["python"].versions)
        self.assertNotIn("${{", by_name["python"].versions)
        self.assertEqual(by_name["node"].classification, "assumed")
        self.assertEqual(by_name["uv"].classification, "assumed")
        self.assertEqual(by_name["yarn"].classification, "assumed")
        for tool in ("pytest", "ruff", "mypy", "black"):
            self.assertEqual(by_name[tool].classification, "assumed")
        self.assertNotIn("pre-commit", by_name)
        self.assertNotIn("fastapi", by_name)
        self.assertNotIn("docker/setup-buildx-action", by_name)
        self.assertFalse(first.is_closed())
        self.assertEqual(
            {item.classification for item in first.items} <= inventory.CLOSED_CLASSES,
            True,
        )

    def test_json_report_is_stable(self) -> None:
        _closed_fixture(self.root)
        scanned = self.scan()
        payload = scanned.to_dict()
        self.assertEqual(payload["task_key"], inventory.TASK_KEY)
        self.assertEqual(payload["conflict_domain"], inventory.CONFLICT_DOMAIN)
        self.assertTrue(payload["closed"])
        encoded = json.dumps(payload, sort_keys=True)
        self.assertEqual(encoded, json.dumps(json.loads(encoded), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
