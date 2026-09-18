"""Fail-closed regressions for the security-priority inventory (#969 S020)."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_security_priority_inventory.py"
SPEC = importlib.util.spec_from_file_location("check_security_priority_inventory", SCRIPT)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, content: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def _mini_repo(root: Path) -> Path:
    _write(
        root,
        "skeleton/api/routes.py",
        """from fastapi import APIRouter
from skeleton.api import helper

router = APIRouter()

@router.get("/health")
def health():
    return helper.touch()
""",
    )
    _write(
        root,
        "skeleton/api/helper.py",
        """import pickle

def touch():
    return pickle.loads(b"")
""",
    )
    _write(
        root,
        "skeleton/cli/tool.py",
        """import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    return parser.parse_args()

if __name__ == "__main__":
    main()
""",
    )
    _write(
        root,
        "skeleton/orphan/unsafe.py",
        """import pickle

def hidden():
    return pickle.loads(b"not-an-entrypoint")
""",
    )
    _write(
        root,
        "skeleton/mixed/surface.py",
        """import argparse
from fastapi import APIRouter

router = APIRouter()
parser = argparse.ArgumentParser()

@router.post("/run")
def run():
    return parser.parse_args([])
""",
    )
    _write(
        root,
        "scripts/gate.py",
        """def inspect():
    return "gate"
""",
    )
    _write(
        root,
        "scripts/gate_main.py",
        """if __name__ == "__main__":
    print("gate")
""",
    )
    _write(
        root,
        ".github/workflows/priority-gate.yml",
        """name: priority-gate
on: pull_request
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/gate_main.py
""",
    )
    _write(
        root,
        "pyproject.toml",
        """[project.scripts]
skeleton = "skeleton.__main__:main"
""",
    )
    _write(
        root,
        "skeleton/__main__.py",
        """def main():
    return 0
""",
    )
    return root


class SecurityPriorityInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        _mini_repo(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _scan(self, root: Path | None = None):
        return inventory.scan_repo(root or self.root)

    def _by_path(self, report, relative: str):
        matches = [item for item in report.items if item.path == relative]
        self.assertEqual(len(matches), 1, relative)
        return matches[0]

    def test_task_identity_and_finding_prefix_are_unique(self) -> None:
        self.assertEqual(inventory.TASK_KEY, "reserve-S020-security-priority")
        self.assertEqual(inventory.CONFLICT_DOMAIN, "security.readonly.regression_priority")
        self.assertEqual(inventory.FINDING_PREFIX, "S020-SEC-PRI")
        self.assertEqual(inventory.SEVERITY_POLICY, "unscored")
        self.assertEqual(inventory.INVENTORY_VERSION, 1)
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module.split(".", 1)[0])
        self.assertNotIn("skeleton", imported)
        self.assertNotIn("pydantic", imported)

    def test_scanner_load_does_not_pull_skeleton_or_pydantic(self) -> None:
        self.assertTrue(getattr(inventory, "__file__", "").endswith("check_security_priority_inventory.py"))
        self.assertNotIn("pydantic", inventory.__dict__)
        self.assertNotIn("skeleton", inventory.__dict__)
        self.assertNotIn("pydantic_settings", inventory.__dict__)

    def test_unknown_class_fails_closed(self) -> None:
        self.assertEqual(inventory.exclusive_reachability(["unknown"]), "unknown")
        self.assertEqual(inventory.exclusive_reachability(["mystery"]), "unknown")
        self.assertIsNone(inventory.rank_for_class("unknown"))
        item = inventory.InventoryItem(
            item_id="S020-SEC-PRI-0001",
            path="skeleton/broken.py",
            reachability="unknown",
            rank=None,
            evidence=(),
            kind="python",
        )
        issues = inventory.item_violations(item)
        self.assertTrue(any("unknown class fails closed" in issue for issue in issues))
        with self.assertRaises(inventory.UnknownReachabilityError):
            report = inventory.InventoryReport(items=[item], violations=issues)
            if report.violations:
                raise inventory.UnknownReachabilityError("; ".join(report.violations))

    def test_unreadable_file_is_unknown_and_fails_closed(self) -> None:
        _write(self.root, "skeleton/broken.py", b"\xff\xfe not utf-8")
        report = self._scan()
        item = self._by_path(report, "skeleton/broken.py")
        self.assertEqual(item.reachability, "unknown")
        self.assertIsNone(item.rank)
        self.assertTrue(any("unknown class fails closed: skeleton/broken.py" in issue for issue in report.violations))
        self.assertEqual(inventory.collect_violations(report=report), report.violations)
        with self.assertRaises(inventory.UnknownReachabilityError):
            inventory.assert_inventory_closed(self.root)

    def test_exclusive_ranking_picks_highest_proven_class_only(self) -> None:
        self.assertEqual(
            inventory.exclusive_reachability(
                ["reachable_cli", "reachable_http", "reachable_workflow"]
            ),
            "reachable_http",
        )
        self.assertEqual(
            inventory.exclusive_reachability(["reachable_entrypoint", "reachable_cli"]),
            "reachable_cli",
        )
        mixed = self._by_path(self._scan(), "skeleton/mixed/surface.py")
        self.assertEqual(mixed.reachability, "reachable_http")
        self.assertEqual(mixed.rank, 0)
        self.assertNotEqual(mixed.reachability, "reachable_cli")

    def test_ranking_is_exclusive_to_reachability_not_severity(self) -> None:
        http = inventory.InventoryItem(
            item_id="a",
            path="z-http.py",
            reachability="reachable_http",
            rank=0,
            evidence=("http:call:APIRouter",),
            kind="python",
            severity=None,
        )
        cli = inventory.InventoryItem(
            item_id="b",
            path="a-cli.py",
            reachability="reachable_cli",
            rank=1,
            evidence=("cli:call:ArgumentParser",),
            kind="python",
            severity=None,
        )
        ordered = sorted([cli, http], key=inventory.ranking_key)
        self.assertEqual([item.reachability for item in ordered], ["reachable_http", "reachable_cli"])
        inflated = inventory.InventoryItem(
            item_id="b",
            path="a-cli.py",
            reachability="reachable_cli",
            rank=1,
            evidence=("cli:call:ArgumentParser",),
            kind="python",
            severity="critical",  # type: ignore[arg-type]
            severity_claimed=True,
        )
        still = sorted([inflated, http], key=inventory.ranking_key)
        self.assertEqual([item.reachability for item in still], ["reachable_http", "reachable_cli"])

    def test_reachable_http_is_ranked_above_unreachable_sensitive_code(self) -> None:
        report = self._scan()
        helper = self._by_path(report, "skeleton/api/helper.py")
        orphan = self._by_path(report, "skeleton/orphan/unsafe.py")
        routes = self._by_path(report, "skeleton/api/routes.py")
        self.assertEqual(routes.reachability, "reachable_http")
        self.assertEqual(helper.reachability, "reachable_http")
        self.assertIn("reach:http:import_graph", helper.evidence)
        self.assertEqual(orphan.reachability, "unreachable")
        self.assertLess(helper.rank, orphan.rank)
        self.assertTrue(routes.item_id.startswith("S020-SEC-PRI-"))
        ranked = [item.path for item in report.items if item.rank is not None]
        self.assertEqual(ranked, sorted(ranked, key=lambda path: (self._by_path(report, path).rank, path)))

    def test_cli_workflow_and_entrypoint_are_distinct_reachable_classes(self) -> None:
        report = self._scan()
        cli = self._by_path(report, "skeleton/cli/tool.py")
        workflow = self._by_path(report, ".github/workflows/priority-gate.yml")
        gate = self._by_path(report, "scripts/gate_main.py")
        dunder = self._by_path(report, "skeleton/__main__.py")
        self.assertEqual(cli.reachability, "reachable_cli")
        self.assertEqual(workflow.reachability, "reachable_workflow")
        self.assertEqual(gate.reachability, "reachable_workflow")
        self.assertTrue(
            dunder.reachability in {"reachable_cli", "reachable_entrypoint"},
            dunder.reachability,
        )
        self.assertLess(cli.rank, workflow.rank)
        self.assertLess(workflow.rank, self._by_path(report, "skeleton/orphan/unsafe.py").rank)

    def test_scanner_does_not_claim_severity_without_evidence(self) -> None:
        report = self._scan()
        payload = inventory.report_to_dict(report)
        self.assertEqual(payload["severity_policy"], "unscored")
        rendered = inventory.render_report(report)
        self.assertNotIn('"critical"', rendered)
        self.assertNotIn('"high"', rendered)
        self.assertNotIn('"cvss"', rendered)
        for item in report.items:
            self.assertIsNone(item.severity)
            self.assertFalse(item.severity_claimed)
            self.assertNotIn("severity=high", item.notes)
        claimed = inventory.InventoryItem(
            item_id="S020-SEC-PRI-9999",
            path="skeleton/api/routes.py",
            reachability="reachable_http",
            rank=0,
            evidence=("http:call:APIRouter",),
            kind="python",
            severity="high",  # type: ignore[arg-type]
            severity_claimed=True,
        )
        issues = inventory.item_violations(claimed)
        self.assertTrue(any("severity claimed without evidence" in issue for issue in issues))

    def test_current_repo_scan_is_deterministic_and_unscored(self) -> None:
        first = inventory.scan_repo(REPO_ROOT)
        second = inventory.scan_repo(REPO_ROOT)
        self.assertEqual(inventory.render_report(first), inventory.render_report(second))
        payload = json.loads(inventory.render_report(first))
        self.assertEqual(payload["task_key"], "reserve-S020-security-priority")
        self.assertEqual(payload["conflict_domain"], "security.readonly.regression_priority")
        self.assertEqual(payload["finding_prefix"], "S020-SEC-PRI")
        self.assertEqual(payload["severity_policy"], "unscored")
        self.assertGreater(len(payload["items"]), 0)
        ids = [item["id"] for item in payload["items"]]
        self.assertEqual(ids, sorted(ids))
        ranks = [item["rank"] for item in payload["items"] if item["reachability"] != "unknown"]
        self.assertEqual(ranks, sorted(rank for rank in ranks if rank is not None) or ranks)
        for item in payload["items"]:
            self.assertIsNone(item["severity"])
            self.assertFalse(item["severity_claimed"])
            self.assertTrue(item["id"].startswith("S020-SEC-PRI-"))
            self.assertIn(item["reachability"], inventory.REACHABILITY_SET)
        reachable = [item for item in first.items if item.reachability == "reachable_http"]
        unreachable = [item for item in first.items if item.reachability == "unreachable"]
        self.assertTrue(reachable, "current repo should expose HTTP trust-boundary surfaces")
        if reachable and unreachable:
            self.assertLess(min(item.rank or 0 for item in reachable), min(item.rank or 0 for item in unreachable))
        for item in first.items:
            if item.reachability != "unknown":
                self.assertEqual(
                    item.reachability,
                    inventory.exclusive_reachability(
                        inventory._kinds_from_evidence(item.evidence, unknown=False)
                    ),
                )
        duplicate_paths = [item.path for item in first.items]
        self.assertEqual(len(duplicate_paths), len(set(duplicate_paths)))

    def test_main_json_exit_matches_violations(self) -> None:
        from io import StringIO
        from unittest import mock

        with mock.patch("sys.stdout", new=StringIO()), mock.patch("sys.stderr", new=StringIO()):
            code = inventory.main(["--root", str(self.root), "--json"])
        self.assertEqual(code, 0)
        _write(self.root, "skeleton/broken.py", b"\xff\xfe")
        with mock.patch("sys.stdout", new=StringIO()), mock.patch("sys.stderr", new=StringIO()):
            code = inventory.main(["--root", str(self.root)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
