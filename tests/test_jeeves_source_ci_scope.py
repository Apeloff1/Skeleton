"""Fail-closed CI fanout and source-qualification path coverage tests."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts.check_ci_workflow_tiers import audit, events
from scripts.check_jeeves_source_ci_scope import (
    GATES, ROOT, _no_duplicate_keys, changed_paths, load_registry, selected_gates,
)

CHILDREN = {
    "integrated": "jeeves-integrated-source-qualification.yml",
    "sqlite": "jeeves-native-sqlite-source-qualification.yml",
    "laptop": "jeeves-laptop-dispatcher-source-tests.yml",
}


def _pr_patterns(text: str) -> set[str]:
    """Extract path values only from the top-level pull_request trigger."""
    section = text.split("\n  pull_request:\n", 1)[1].split("\n  push:\n", 1)[0]
    return {
        line.strip()[3:-1]
        for line in section.splitlines()
        if line.strip().startswith("- '") and line.strip().endswith("'")
    }


class JeevesSourceScopeTests(unittest.TestCase):
    def test_registry_and_auto_admission_ceiling_are_aligned(self) -> None:
        registry = load_registry()
        self.assertEqual(set(registry), set(GATES))
        self.assertEqual(audit(ROOT), [])

    def test_every_governed_path_remains_a_parent_pull_request_trigger(self) -> None:
        parent = (ROOT / ".github/workflows/sealed-context-guard.yml").read_text()
        triggers = _pr_patterns(parent)
        for gate, patterns in load_registry().items():
            with self.subTest(gate=gate):
                self.assertTrue(set(patterns) <= triggers, gate)
        self.assertIn("\n  pull_request:\n", parent)
        self.assertNotIn("    branches: [main]\n", parent)

    def test_all_three_qualifications_remain_source_bound_reusable_jobs(self) -> None:
        parent = (ROOT / ".github/workflows/sealed-context-guard.yml").read_text()
        self.assertIn("needs.source-scope", parent.replace("jeeves-source-scope", "source-scope"))
        for gate, name in CHILDREN.items():
            child = (ROOT / ".github/workflows" / name).read_text()
            with self.subTest(gate=gate):
                self.assertEqual(events(child), {"workflow_call", "workflow_dispatch"})
                self.assertIn("permissions:\n  contents: read", child)
                self.assertIn("persist-credentials: false", child)
                self.assertIn("uses: ./.github/workflows/" + name, parent)
                self.assertIn("needs.jeeves-source-scope.outputs." + gate, parent)

    def test_source_only_gates_match_old_specific_scope(self) -> None:
        registry = load_registry()
        self.assertEqual(
            selected_gates(("skeleton/testing/test_ai_git_knowledge.py",), registry),
            {"sealed": False, "integrated": True, "sqlite": False, "laptop": False},
        )
        self.assertTrue(selected_gates(
            ("skeleton/ai/runtime/operational_ai/laptop_runtime/dispatcher.py",), registry,
        )["laptop"])
        self.assertTrue(selected_gates(
            ("skeleton/jeeves/worlds/accessibility.py",), registry,
        )["integrated"])
        self.assertTrue(selected_gates(("skeleton/context/ledger.py",), registry)["sealed"])
        self.assertEqual(
            selected_gates(("frontend/components/Editor.tsx",), registry),
            dict.fromkeys(GATES, False),
        )
        self.assertEqual(
            selected_gates(("scripts/check_jeeves_source_ci_scope.py",), registry),
            dict.fromkeys(GATES, True),
        )

    def test_git_delta_is_null_delimited_no_shell_and_never_runs_user_paths(self) -> None:
        with mock.patch(
            "scripts.check_jeeves_source_ci_scope.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout=b"skeleton/jeeves/worlds/testimony.py\x00",
            ),
        ) as run:
            self.assertEqual(changed_paths(ROOT), (
                "skeleton/jeeves/worlds/testimony.py",
            ))
            args, kwargs = run.call_args
            self.assertEqual(args[0][:3], ["git", "diff", "--no-renames"])
            self.assertEqual(args[0][-3:], ["HEAD^1", "HEAD", "--"])
            self.assertIs(kwargs["shell"], False)
            self.assertEqual(kwargs["cwd"], ROOT)

    def test_missing_or_hostile_git_delta_fails_closed(self) -> None:
        for payload in (
            b"", b"truncated", b"../operator-secret\x00",
            b"/etc/passwd\x00", b"safe/path.py\x00safe/path.py\x00",
            b"safe\\\\path.py\x00", b"invalid-\xff\x00",
        ):
            with self.subTest(payload=payload), mock.patch(
                "scripts.check_jeeves_source_ci_scope.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=payload,
                ),
            ):
                with self.assertRaises((ValueError, UnicodeError)):
                    changed_paths(ROOT)

    def test_registry_rejects_duplicates_and_links(self) -> None:
        with self.assertRaises(ValueError):
            _no_duplicate_keys([("gates", {}), ("gates", {})])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "machine").mkdir()
            (root / "machine/jeeves_source_ci_trigger_registry.json").symlink_to(
                ROOT / "machine/jeeves_source_ci_trigger_registry.json",
            )
            with self.assertRaises(ValueError):
                load_registry(root)

    def test_dot_prefixed_github_workflow_path_is_admitted(self) -> None:
        from scripts.check_jeeves_source_ci_scope import _safe_path

        self.assertTrue(_safe_path(".github/workflows/sealed-context-guard.yml"))
        self.assertFalse(_safe_path("../outside"))
        selected = selected_gates(
            [".github/workflows/jeeves-native-sqlite-source-qualification.yml"],
            load_registry(),
        )
        self.assertTrue(selected["sqlite"])

    def test_unsafe_changed_path_refuses_positive_gate(self) -> None:
        with self.assertRaises(ValueError):
            selected_gates(["../unsafe"], load_registry())
        with self.assertRaises(ValueError):
            selected_gates([], load_registry())


if __name__ == "__main__":
    unittest.main()
