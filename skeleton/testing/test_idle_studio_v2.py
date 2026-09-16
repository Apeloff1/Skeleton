from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.automation.chatgpt_adapter import ReasoningResult
from skeleton.automation.idle_studio import (
    ChangeProposal,
    ProposedFile,
    StudioConfig,
    WorkItem,
    assign_workers,
)
from skeleton.automation.idle_studio_v2 import (
    PACKAGE_VERSION,
    ResearchDecision,
    ReviewDecision,
    VerificationDecision,
    choose_reviewer,
    choose_squad,
    entry_for,
    plan_tasks,
    planner_evidence,
    redact,
    validate,
    write_json,
)


class _FakeReasoner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests = []

    def reason(self, request):  # noqa: ANN001
        self.requests.append(request)
        return ReasoningResult(True, self.text)


class IdleStudioV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = StudioConfig(
            active_workers=8,
            tasks_per_run=4,
            max_model_calls=9,
            max_files_per_change=4,
            max_file_bytes=10_000,
            max_total_change_bytes=20_000,
            max_open_studio_prs=12,
            dry_run=True,
        )

    @staticmethod
    def _tasks(count: int = 4) -> list[WorkItem]:
        return [
            WorkItem(
                key=f"issue:{index}",
                kind="security" if index == 0 else "backlog",
                title=f"Task {index}",
                evidence="evidence " * 20,
                priority=100 - index,
            )
            for index in range(count)
        ]

    def test_planner_filters_unknown_duplicate_keys_and_caps_selection(self) -> None:
        tasks = self._tasks()
        reasoner = _FakeReasoner(
            json.dumps(
                {
                    "task_keys": ["unknown", "issue:2", "issue:2", "issue:0", "issue:1"],
                    "rationale": "Prefer the security repair and one bounded backlog item.",
                }
            )
        )
        decision = plan_tasks(reasoner, tasks, 2)
        self.assertEqual(decision.task_keys, ("issue:2", "issue:0"))
        self.assertEqual(len(reasoner.requests), 1)

    def test_planner_evidence_respects_reasoner_item_limits(self) -> None:
        evidence = planner_evidence(self._tasks(30))
        self.assertEqual(len(evidence), 20)
        self.assertTrue(all(len(item) < 20_000 for item in evidence))

    def test_four_agent_squad_is_stable_distinct_and_security_aware(self) -> None:
        task = self._tasks(1)[0]
        builder = assign_workers([task], 1)[0][1]
        first = choose_squad(task, builder)
        second = choose_squad(task, builder)
        self.assertEqual(first, second)
        self.assertEqual(len(set(first.worker_ids)), 4)
        self.assertEqual(first.researcher.role, "research-benchmark")
        self.assertEqual(first.reviewer.role, "security")
        self.assertEqual(first.verifier.role, "testing")

    def test_independent_reviewer_is_stable_and_not_the_builder(self) -> None:
        task = self._tasks(1)[0]
        builder = assign_workers([task], 1)[0][1]
        first = choose_reviewer(task, builder)
        second = choose_reviewer(task, builder)
        self.assertEqual(first, second)
        self.assertNotEqual(first.worker_id, builder.worker_id)
        self.assertEqual(first.role, "security")

    def test_recursive_redaction_removes_nested_credentials(self) -> None:
        bearer = "abcdefghijkl" + "mnopqrstuvwxyz"
        api_key = "sk-" + "abcdefghijklmnop" + "QRSTUV"
        token = "super" + "secretvalue"
        value = {
            "authorization": f"Authorization: Bearer {bearer}",
            "nested": [f"api_key={api_key}", {"token": f"token={token}"}],
        }
        encoded = json.dumps(redact(value))
        self.assertNotIn(bearer, encoded)
        self.assertNotIn(api_key, encoded)
        self.assertNotIn(token, encoded)
        self.assertIn("REDACTED", encoded)

    def _approved_entry(self):
        task = self._tasks(1)[0]
        builder = assign_workers([task], 1)[0][1]
        squad = choose_squad(task, builder)
        proposal = ChangeProposal(
            summary="Add a bounded regression helper.",
            files=(ProposedFile("skeleton/example.py", "def answer():\n    return 42\n"),),
            verification_notes=("CI must exercise the helper",),
        )
        research = ResearchDecision(
            findings=("The helper is isolated.",),
            risks=("Keep the API additive.",),
            recommended_checks=("focused unit test",),
        )
        review = ReviewDecision(True, "Small, scoped, and syntactically valid.")
        verification = VerificationDecision(
            True,
            "Credential-free CI can prove the behavior.",
            ("focused unit test",),
        )
        return task, squad, research, review, verification, proposal

    def test_sealed_package_round_trip_requires_four_distinct_workers_and_two_approvals(self) -> None:
        task, squad, research, review, verification, proposal = self._approved_entry()
        package = {
            "version": PACKAGE_VERSION,
            "status": "ready",
            "base_sha": "a" * 40,
            "planner": None,
            "entries": [entry_for(task, squad, research, review, verification, proposal)],
        }
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "package.json"
            write_json(path, package)
            self.assertEqual(validate(path, self.config), 0)

            data = json.loads(path.read_text(encoding="utf-8"))
            data["entries"][0]["review"]["approve"] = False
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate(path, self.config)

            data = package
            data["entries"][0]["verification"]["approve"] = False
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate(path, self.config)

    def test_sealed_package_rejects_worker_reuse_across_roles(self) -> None:
        task, squad, research, review, verification, proposal = self._approved_entry()
        entry = entry_for(task, squad, research, review, verification, proposal)
        entry["verifier"] = dict(entry["reviewer"])
        package = {
            "version": PACKAGE_VERSION,
            "status": "ready",
            "base_sha": "b" * 40,
            "planner": None,
            "entries": [entry],
        }
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "package.json"
            write_json(path, package)
            with self.assertRaises(ValueError):
                validate(path, self.config)

    def test_old_two_agent_package_version_fails_closed(self) -> None:
        task, squad, research, review, verification, proposal = self._approved_entry()
        package = {
            "version": 1,
            "status": "ready",
            "base_sha": "c" * 40,
            "planner": None,
            "entries": [entry_for(task, squad, research, review, verification, proposal)],
        }
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "package.json"
            write_json(path, package)
            with self.assertRaises(ValueError):
                validate(path, self.config)


if __name__ == "__main__":
    unittest.main()
