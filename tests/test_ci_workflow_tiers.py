"""Regression checks for archived specialist workflows and lean active CI."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.check_ci_workflow_tiers import ROOT, _read_reviewed, audit, events


class WorkflowTierTests(unittest.TestCase):
    def test_repo_tiers_are_consistent(self):
        self.assertEqual(audit(ROOT), [])

    def test_masterplan_workflow_references_resolve(self):
        """Signed masterplan evidence paths must continue to name real workflows."""
        masterplan = json.loads(
            (ROOT / "machine/ai_master_plan.json").read_text(encoding="utf-8")
        )
        referenced = set(re.findall(
            r"\.github/workflows/[A-Za-z0-9._-]+\.ya?ml",
            json.dumps(masterplan),
        ))
        self.assertTrue(referenced, "masterplan must retain workflow evidence")
        missing = sorted(
            path for path in referenced if not (ROOT / path).is_file()
        )
        self.assertEqual(missing, [], "masterplan references missing workflows")

    def test_auxiliary_admissions_are_manual_only(self):
        """Keep the reviewed automatic-inventory quota and required security gates."""
        for name in ("historical-zero-job-canary.yml", "local-ai-boilerplate.yml"):
            source = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertEqual(events(source), {"workflow_dispatch"}, name)
        canary = (ROOT / ".github/workflows/historical-zero-job-canary.yml").read_text(encoding="utf-8")
        self.assertIn("os.environ.get('GH_ACTOR') != 'Apeloff1'", canary)
        self.assertIn("os.environ.get('GH_EVENT') != 'workflow_dispatch'", canary)
        readiness = (ROOT / ".github/workflows/merge-readiness.yml").read_text(encoding="utf-8")
        self.assertIn("skeleton/testing --tb=short", readiness)
        self.assertNotIn("--ignore=skeleton/testing/test_local_ai_boilerplate.py", readiness)

    def test_shadow_top_level_trigger_declarations_fail_closed(self):
        """Reject additional top-level on keys regardless of inline syntax."""
        baseline = "name: CI\non:\n  pull_request:\njobs:\n  build:\n"
        self.assertEqual(events(baseline), {"pull_request"})
        for shadow in (
            "on: [push]",
            "on: {push: {}}",
            "on: # second declaration",
            "on :",
            "on : [push]",
            "on:\t",
        ):
            with self.subTest(shadow=shadow):
                with self.assertRaises(ValueError):
                    events(baseline + shadow + "\n")

    def test_registry_rejects_duplicate_keys_and_unhashable_trigger_profiles(self):
        """Malformed registry inputs must fail closed with diagnostics, not exceptions."""
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "machine").mkdir()
            source = (ROOT / "machine/ci_workflow_tiers.json").read_text(encoding="utf-8")
            registry_path = root / "machine/ci_workflow_tiers.json"
            # Duplicate top-level keys previously allowed the final inventory to
            # silently replace the reviewed one.
            registry_path.write_text(
                source.replace(
                    '"schema": "skeleton.ci.workflow_tiers.v1",',
                    '"schema": "skeleton.ci.workflow_tiers.v1",\n'
                    '  "schema": "skeleton.ci.workflow_tiers.v1",',
                    1,
                ),
                encoding="utf-8",
            )
            self.assertTrue(any("duplicate CI registry key" in p for p in audit(root)))
            registry = json.loads(source)
            profile_name = next(iter(registry["automatic_event_triggers"]))
            for malformed in ([{"push": True}], [["push"]], [None], [42]):
                with self.subTest(malformed=malformed):
                    registry["automatic_event_triggers"][profile_name] = malformed
                    registry_path.write_text(json.dumps(registry), encoding="utf-8")
                    self.assertIn("invalid explicit automatic event trigger profiles", audit(root))

    def test_reviewed_evidence_read_is_bounded(self):
        """Oversized registries and workflow files must fail before parsing."""
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "machine").mkdir()
            (root / ".github/workflows").mkdir(parents=True)
            registry = root / "machine/ci_workflow_tiers.json"
            registry.write_bytes(b" " * (1024 * 1024 + 1))
            self.assertTrue(any(
                "oversized CI evidence file" in problem for problem in audit(root)
            ))
            registry.write_text(
                (ROOT / "machine/ci_workflow_tiers.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            workflow = root / ".github/workflows/oversized.yml"
            workflow.write_bytes(b"on:\\n  pull_request:\\n" + b"#" * (1024 * 1024))
            self.assertTrue(any(
                "oversized CI evidence file" in problem for problem in audit(root)
            ))

    def test_descriptor_anchored_evidence_custody(self):
        """File and parent symlinks, traversal and nonregular payloads fail closed."""
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "safe").mkdir()
            (root / "safe" / "policy.yml").write_text("on:\\n  push:\\n")
            self.assertIn("push", _read_reviewed(root, Path("safe/policy.yml")))
            (root / "file-link.yml").symlink_to(root / "safe/policy.yml")
            (root / "dir-link").symlink_to(root / "safe", target_is_directory=True)
            for candidate in (Path("file-link.yml"), Path("dir-link/policy.yml"),
                              Path("../outside"), Path("/etc/passwd"), Path("safe")):
                with self.subTest(candidate=str(candidate)), self.assertRaises(
                    (OSError, ValueError)
                ):
                    _read_reviewed(root, candidate)
            if hasattr(os, "mkfifo"):
                fifo = root / "fifo"
                os.mkfifo(fifo)
                with self.assertRaises((OSError, ValueError)):
                    _read_reviewed(root, Path("fifo"))

    def test_hardlinked_evidence_cannot_alias_reviewed_registry_or_workflow(self):
        """An inode shared with an unreviewed path is not immutable evidence."""
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "machine").mkdir()
            (root / ".github/workflows").mkdir(parents=True)
            registry = root / "machine/ci_workflow_tiers.json"
            registry.write_text(
                (ROOT / "machine/ci_workflow_tiers.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            alias = root / "registry-alias.json"
            try:
                os.link(registry, alias)
            except (OSError, NotImplementedError):
                self.skipTest("hardlinks unavailable on this filesystem")
            self.assertTrue(any(
                "hardlink aliases" in problem for problem in audit(root)
            ))
            alias.unlink()
            workflow = root / ".github/workflows/extra.yml"
            workflow.write_text("on:\\n  workflow_dispatch:\\njobs:\\n", encoding="utf-8")
            alias = root / "workflow-alias.yml"
            os.link(workflow, alias)
            with self.assertRaisesRegex(ValueError, "hardlink aliases"):
                _read_reviewed(root, Path(".github/workflows/extra.yml"))
            alias.unlink()
            self.assertIn("workflow_dispatch", _read_reviewed(
                root, Path(".github/workflows/extra.yml")
            ))

    def test_linked_evidence_diagnostics_are_stable(self):
        """A linked parent and a linked file report custody failure, not success."""
        with TemporaryDirectory() as temp:
            root = Path(temp)
            trusted = root / "trusted"
            trusted.mkdir()
            (trusted / "policy.yml").write_text("on:\\n  push:\\n", encoding="utf-8")
            self.assertIn("push", _read_reviewed(root, Path("trusted/policy.yml")))
            for name, target, is_dir in (
                ("linked-file.yml", trusted / "policy.yml", False),
                ("linked-parent", trusted, True),
            ):
                link = root / name
                try:
                    link.symlink_to(target, target_is_directory=is_dir)
                except (OSError, NotImplementedError):
                    self.skipTest("symlinks unavailable on this filesystem")
                path = Path(name) / "policy.yml" if is_dir else Path(name)
                with self.subTest(path=str(path)), self.assertRaisesRegex(
                    (OSError, ValueError), "linked CI evidence path"
                ):
                    _read_reviewed(root, path)
                link.unlink()

    def test_event_parser(self):
        self.assertEqual(events("name: Job\non:\n  workflow_dispatch:\n\njobs:\n"), {"workflow_dispatch"})
        self.assertEqual(events("on:\n  pull_request:\n  push:\njobs:\n"), {"pull_request", "push"})
        for invalid in (
            "on: [push]\njobs:\n",
            "on:\n  push:\n  push:\njobs:\n",
            "on:\n  pull_request: {branches: [main]}\njobs:\n",
            "on:\n  workflow_dispatch:\njobs:\non:\n  push:\n",
            "on:\n  - push\njobs:\n",
            "on:\njobs:\n",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                events(invalid)

    def test_specialists_are_archived_and_active_core_remains_required(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows-archive").mkdir()
            (root / "machine").mkdir()
            registry = json.loads((ROOT / "machine/ci_workflow_tiers.json").read_text())
            (root / "machine/ci_workflow_tiers.json").write_text(json.dumps(registry))
            # Include all active YAML workflows so count and core contracts are realistic.
            for source in (ROOT / ".github/workflows").glob("*.yml"):
                (root / ".github/workflows" / source.name).write_text(source.read_text())
            for source in (ROOT / ".github/workflows").glob("*.yaml"):
                (root / ".github/workflows" / source.name).write_text(source.read_text())
            for name in registry["specialized_manual_only"] + registry["required_reusable_workflows"]:
                source = ROOT / ".github/workflows-archive" / name
                (root / ".github/workflows-archive" / name).write_text(source.read_text())
            self.assertEqual(audit(root), [])
            # A linked archive directory must not redirect every specialist
            # to unreviewed files, even when their contents look legitimate.
            archive_dir = root / ".github/workflows-archive"
            moved_archive = root / "external-archive"
            archive_dir.rename(moved_archive)
            try:
                try:
                    archive_dir.symlink_to(moved_archive, target_is_directory=True)
                except (OSError, NotImplementedError):
                    # Some Windows runners prohibit creating directory links.
                    pass
                else:
                    try:
                        self.assertTrue(any(
                            "linked CI evidence path" in problem for problem in audit(root)
                        ))
                    finally:
                        archive_dir.unlink()
            finally:
                moved_archive.rename(archive_dir)
            self.assertEqual(audit(root), [])
            # All reviewed evidence must be ordinary checkout files, including
            # archived gates and the registry (not only active YAML files).
            archive_gate = root / ".github/workflows-archive" / registry["specialized_manual_only"][0]
            registry_file = root / "machine/ci_workflow_tiers.json"
            for reviewed in (archive_gate, registry_file):
                with self.subTest(linked_evidence=str(reviewed)):
                    original = reviewed.read_text(encoding="utf-8")
                    target = root / ("outside-" + reviewed.name)
                    target.write_text(original, encoding="utf-8")
                    reviewed.unlink()
                    try:
                        reviewed.symlink_to(target)
                    except (OSError, NotImplementedError):
                        reviewed.write_text(original, encoding="utf-8")
                        target.unlink()
                        self.skipTest("symlinks unavailable on this filesystem")
                    try:
                        self.assertTrue(any(
                            "linked CI evidence path" in problem for problem in audit(root)
                        ))
                    finally:
                        reviewed.unlink()
                        reviewed.write_text(original, encoding="utf-8")
                        target.unlink()
            self.assertEqual(audit(root), [])
            reusable = root / ".github/workflows" / registry["required_reusable_workflows"][0]
            reusable_original = reusable.read_text()
            reusable.write_text(reusable_original.replace("  workflow_call:", "  pull_request:"))
            self.assertTrue(any("required reusable workflow must be callable" in p for p in audit(root)))
            reusable.write_text(reusable_original)
            readiness = root / ".github/workflows/merge-readiness.yml"
            readiness_original = readiness.read_text()
            readiness.write_text(readiness_original.replace(
                "uses: ./.github/workflows/ci.yml", "uses: ./.github/workflows/missing-ci.yml"
            ))
            self.assertTrue(any("required reusable workflow not called" in p for p in audit(root)))
            readiness.write_text(readiness_original)
            evidence = root / ".github/workflows" / "signed-evidence-manual.yml"
            evidence.write_text(
                "name: Signed evidence\n"
                "on:\n"
                "  workflow_dispatch:\n"
                "jobs:\n"
                "  hold:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - run: echo hold\n",
                encoding="utf-8",
            )
            self.assertEqual(audit(root), [])
            evidence.unlink()
            # An active workflow symlink must never be followed, even when its
            # target contains a syntactically valid manual-only workflow.
            # The audit must reject the link rather than accepting a gate
            # whose actual source can change outside the reviewed inventory.
            linked = root / ".github/workflows" / "linked-manual.yml"
            target = root / "external-workflow.yml"
            target.write_text(
                "name: External\\non:\\n  workflow_dispatch:\\njobs:\\n",
                encoding="utf-8",
            )
            try:
                linked.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this filesystem")
            self.assertTrue(any(
                "linked-manual.yml: active workflow must not be a symlink" in problem
                for problem in audit(root)
            ))
            linked.unlink()
            target.unlink()
            self.assertEqual(audit(root), [])
            # An unregistered PR subscriber must fail even if the numeric
            # quota would otherwise have spare capacity.
            evidence.write_text(
                "name: Rogue workflow\n"
                "on:\n"
                "  pull_request:\n"
                "jobs:\n"
                "  hold:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - run: echo hold\n",
                encoding="utf-8",
            )
            self.assertTrue(any(
                "unregistered automatic workflows" in item
                for item in audit(root)
            ))
            evidence.unlink()
            # Silently deactivating a required source gate must also fail.
            expected_gate = root / ".github/workflows/first-install-source-qualification.yml"
            original_gate = expected_gate.read_text(encoding="utf-8")
            self.assertIn("  pull_request:", original_gate)
            expected_gate.write_text(
                original_gate.replace("  pull_request:", "  workflow_dispatch:", 1),
                encoding="utf-8",
            )
            self.assertTrue(any(
                "expected automatic workflows not triggered" in item
                for item in audit(root)
            ))
            expected_gate.write_text(original_gate, encoding="utf-8")
            # Changing a trusted PR gate into a push-only subscriber preserves
            # the total automatic count but violates its approved event scope.
            expected_gate.write_text(
                original_gate.replace("  pull_request:", "  push:", 1),
                encoding="utf-8",
            )
            self.assertTrue(any(
                "event admission trigger drift" in item for item in audit(root)
            ))
            expected_gate.write_text(original_gate, encoding="utf-8")
            self.assertEqual(audit(root), [])
            for index in range(10):
                (
                    root / ".github/workflows" / f"automatic-extra-{index}.yml"
                ).write_text(
                    "name: extra\non:\n  pull_request:\njobs:\n  x:\n"
                    "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
                    encoding="utf-8",
                )
            self.assertTrue(
                any("unexpected active workflow count" in item for item in audit(root))
            )
            for index in range(10):
                (root / ".github/workflows" / f"automatic-extra-{index}.yml").unlink()
            name = registry["specialized_manual_only"][0]
            spec = root / ".github/workflows-archive" / name
            original = spec.read_text()
            spec.write_text(original.replace("  workflow_dispatch:", "  pull_request:\n  workflow_dispatch:"))
            self.assertTrue(any("archived specialist" in p for p in audit(root)))
            spec.write_text(original)
            (root / ".github/workflows" / name).write_text(original)
            self.assertTrue(any("unexpectedly active" in p for p in audit(root)))
            (root / ".github/workflows" / name).unlink()
            core = root / ".github/workflows" / registry["core_automatic_pr"][0]
            core.write_text("name: disabled\non:\n  workflow_dispatch:\njobs:\n")
            self.assertTrue(any("core PR trigger missing" in p for p in audit(root)))


if __name__ == "__main__":
    unittest.main()
