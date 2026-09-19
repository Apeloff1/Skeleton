from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skeleton.automation import secretary, specialist_bots, supervisor


FP = "a" * 64
REPO = "Apeloff1/Skeleton"


class SupervisorEnvelopeTests(unittest.TestCase):
    def snapshot(self) -> supervisor.SupervisorSnapshot:
        return supervisor.SupervisorSnapshot(
            repository=REPO,
            observed_at=1_700_000_000,
            issues=({"number": 1, "title": "CI failure"},),
            pull_requests=({"number": 2, "title": "repair", "mergeStateStatus": "BLOCKED"},),
            workflow_runs=({"databaseId": 3, "conclusion": "failure", "name": "quality"},),
        )

    def test_snapshot_fingerprint_is_stable_across_observation_time(self) -> None:
        first = self.snapshot()
        second = supervisor.SupervisorSnapshot(first.repository, first.observed_at + 30, first.issues, first.pull_requests, first.workflow_runs)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_snapshot_fingerprint_changes_with_repository_state(self) -> None:
        first = self.snapshot()
        second = supervisor.SupervisorSnapshot(first.repository, first.observed_at, (), first.pull_requests, first.workflow_runs)
        self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_envelope_round_trip(self) -> None:
        snap = self.snapshot()
        env = supervisor.make_envelope(snap, "repair failing CI")
        plan, fingerprint = secretary.decode_delegation(env.to_base64(), repository=REPO, now=snap.observed_at)
        self.assertEqual(plan, "repair failing CI")
        self.assertEqual(fingerprint, snap.fingerprint)

    def test_envelope_rejects_cross_repository_replay(self) -> None:
        snap = self.snapshot()
        encoded = supervisor.make_envelope(snap, "repair failing CI").to_base64()
        with self.assertRaises(secretary.SecretaryAdmissionError):
            secretary.decode_delegation(encoded, repository="other/repository", now=snap.observed_at)

    def test_envelope_rejects_stale_plan(self) -> None:
        snap = self.snapshot()
        encoded = supervisor.make_envelope(snap, "repair failing CI").to_base64()
        with self.assertRaises(secretary.SecretaryAdmissionError):
            secretary.decode_delegation(encoded, repository=REPO, now=snap.observed_at + secretary.MAX_ENVELOPE_AGE_SECONDS + 1)

    def test_envelope_rejects_far_future_observation(self) -> None:
        snap = self.snapshot()
        encoded = supervisor.make_envelope(snap, "repair failing CI").to_base64()
        with self.assertRaises(secretary.SecretaryAdmissionError):
            secretary.decode_delegation(encoded, repository=REPO, now=snap.observed_at - 301)

    def test_envelope_rejects_malformed_base64(self) -> None:
        with self.assertRaises(secretary.SecretaryAdmissionError):
            secretary.decode_delegation("%%%", repository=REPO, now=1_700_000_000)

    def test_envelope_rejects_unsupported_version(self) -> None:
        payload = base64.b64encode(json.dumps({"version": 99}).encode()).decode()
        with self.assertRaises(secretary.SecretaryAdmissionError):
            secretary.decode_delegation(payload, repository=REPO, now=1_700_000_000)

    def test_envelope_rejects_invalid_fingerprint(self) -> None:
        payload = {"version": 1, "repository": REPO, "snapshot_fingerprint": "nope", "observed_at": 1_700_000_000, "plan": "CI failure"}
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        with self.assertRaises(secretary.SecretaryAdmissionError):
            secretary.decode_delegation(encoded, repository=REPO, now=1_700_000_000)

    def test_emit_github_output_is_single_line_bounded_data(self) -> None:
        snap = self.snapshot()
        env = supervisor.make_envelope(snap, "repair CI")
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "output"
            supervisor.emit_github_output(env, str(target))
            lines = target.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("delegation_b64="))
        self.assertEqual(lines[1], f"snapshot_fingerprint={snap.fingerprint}")

    def test_emit_github_output_rejects_relative_path(self) -> None:
        with self.assertRaises(supervisor.SupervisorError):
            supervisor.emit_github_output(supervisor.make_envelope(self.snapshot(), "repair CI"), "relative-output")

    def test_deterministic_plan_carries_snapshot_identity(self) -> None:
        snap = self.snapshot()
        plan = json.loads(supervisor.deterministic_plan(snap))
        self.assertEqual(plan["snapshot_fingerprint"], snap.fingerprint)
        self.assertEqual(plan["priority_observations"]["open_issue_count"], 1)

    def test_model_plan_falls_back_without_provider(self) -> None:
        snap = self.snapshot()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(supervisor.model_plan(snap), supervisor.deterministic_plan(snap))


class SecretaryRoutingTests(unittest.TestCase):
    def test_route_only_returns_due_registered_workers(self) -> None:
        due = ["root-cause", "security-auditor"]
        self.assertEqual(set(secretary.route("CI build failure and security finding", due)), set(due))

    def test_route_never_exceeds_assignment_budget(self) -> None:
        due = [spec.name for spec in secretary.ADVANCED_BOTS]
        routed = secretary.route("CI workflow failure dependency CVE regression architecture security performance release docs integration contract PR review coverage API schema", due)
        self.assertLessEqual(len(routed), secretary.MAX_ASSIGNMENTS)

    def test_dispatch_rejects_duplicate_workers(self) -> None:
        with self.assertRaises(secretary.SecretaryAdmissionError):
            secretary.dispatch("plan", ["root-cause", "root-cause"], FP)

    def test_dispatch_rejects_unregistered_worker(self) -> None:
        with self.assertRaises(secretary.SecretaryAdmissionError):
            secretary.dispatch("plan", ["arbitrary-module"], FP)

    def test_dispatch_rejects_assignment_budget_overflow(self) -> None:
        with self.assertRaises(secretary.SecretaryAdmissionError):
            secretary.dispatch("plan", [spec.name for spec in secretary.ADVANCED_BOTS[:4]], FP)

    def test_dispatch_stamps_secretary_custody(self) -> None:
        captured = {}
        def fake_run(argv, *, env, timeout):
            captured.update(env)
            class Result:
                returncode = 0
            return Result()
        with patch("skeleton.automation.secretary.subprocess.run", side_effect=fake_run):
            result = secretary.dispatch("CI failure", ["root-cause"], FP)
        self.assertEqual(result[0]["returncode"], 0)
        self.assertEqual(captured["SECRETARY_DELEGATION"], "1")
        self.assertEqual(captured["SECRETARY_WORKER"], "root-cause")
        self.assertEqual(captured["SUPERVISOR_SNAPSHOT_FINGERPRINT"], FP)


class WorkerAdmissionTests(unittest.TestCase):
    def test_direct_worker_invocation_is_rejected(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(specialist_bots.WorkerAdmissionError):
                specialist_bots.admit_worker("root-cause")

    def test_worker_identity_mismatch_is_rejected(self) -> None:
        with patch.dict(os.environ, {"SECRETARY_DELEGATION": "1", "SECRETARY_WORKER": "security-auditor"}, clear=True):
            with self.assertRaises(specialist_bots.WorkerAdmissionError):
                specialist_bots.admit_worker("root-cause")

    def test_valid_secretary_delegation_is_admitted(self) -> None:
        env = {"SECRETARY_DELEGATION": "1", "SECRETARY_WORKER": "root-cause", "SUPERVISOR_SNAPSHOT_FINGERPRINT": FP}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(specialist_bots.admit_worker("root-cause"), FP)

    def test_invalid_supervisor_fingerprint_is_rejected(self) -> None:
        env = {"SECRETARY_DELEGATION": "1", "SECRETARY_WORKER": "root-cause", "SUPERVISOR_SNAPSHOT_FINGERPRINT": "bad"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(specialist_bots.WorkerAdmissionError):
                specialist_bots.admit_worker("root-cause")

    def test_safe_path_rejects_control_planes(self) -> None:
        self.assertFalse(specialist_bots.safe_path(".github/workflows/evil.yml"))
        self.assertFalse(specialist_bots.safe_path("skeleton/automation/supervisor.py"))
        self.assertFalse(specialist_bots.safe_path("skeleton/automation/secretary.py"))
        self.assertFalse(specialist_bots.safe_path("../outside.py"))
        self.assertFalse(specialist_bots.safe_path("deploy/release.py"))
        self.assertTrue(specialist_bots.safe_path("skeleton/runtime.py"))
        self.assertTrue(specialist_bots.safe_path("tests/test_runtime.py"))

    def test_extract_plan_rejects_duplicate_paths(self) -> None:
        raw = json.dumps({"files": [{"path": "tests/test_x.py", "content": "x = 1\n"}, {"path": "tests/test_x.py", "content": "x = 2\n"}]})
        with self.assertRaises(ValueError):
            specialist_bots.extract_plan(raw, 3)

    def test_extract_plan_rejects_total_byte_overflow(self) -> None:
        old = specialist_bots.MAX_TOTAL_PROPOSED_BYTES
        with patch.object(specialist_bots, "MAX_TOTAL_PROPOSED_BYTES", 10):
            raw = json.dumps({"files": [{"path": "tests/test_x.py", "content": "x" * 11}]})
            with self.assertRaises(ValueError):
                specialist_bots.extract_plan(raw, 3)
        self.assertGreater(old, 10)

    def test_generated_python_must_parse(self) -> None:
        with self.assertRaises(RuntimeError):
            specialist_bots.validate_generated_files([{"path": "tests/test_bad.py", "content": "def broken(:\n"}])

    def test_mutation_budget_counts_insertions_and_deletions(self) -> None:
        files = [{"path": "tests/test_x.py", "content": "new\nvalue\n"}]
        with patch("skeleton.automation.specialist_bots.subprocess.check_output", return_value="old\n"):
            self.assertEqual(specialist_bots.validate_mutation_budget(files), 3)

    def test_mutation_budget_fails_closed(self) -> None:
        files = [{"path": "tests/test_x.py", "content": "a\nb\nc\n"}]
        with patch.object(specialist_bots, "MAX_CHANGED_LINES", 2), patch("skeleton.automation.specialist_bots.subprocess.check_output", return_value=""):
            with self.assertRaises(RuntimeError):
                specialist_bots.validate_mutation_budget(files)


if __name__ == "__main__":
    unittest.main()
