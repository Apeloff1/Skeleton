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
    ReviewDecision,
    choose_reviewer,
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
            max_model_calls=6,
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
                    "task_keys": [
                        "unknown",
                        "issue:2",
                        "issue:2",
                        "issue:0",
                        "issue:1",
                    ],
                    "rationale": (
                        "Prefer the security repair and one bounded backlog item."
                    ),
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

    def test_independent_reviewer_is_stable_and_not_the_builder(self) -> None:
        task = self._tasks(1)[0]
        builder = assign_workers([task], 1)[0][1]
        first = choose_reviewer(task, builder)
        second = choose_reviewer(task, builder)
        self.assertEqual(first, second)
        self.assertNotEqual(first.worker_id, builder.worker_id)
        self.assertEqual(first.role, "security")

    def test_recursive_redaction_removes_nested_credentials(self) -> None:
        value = {
            "authorization": (
                "Authorization: Bearer abcdefghijklmnopqrstuvwxyz"
            ),
            "nested": [
                "api_key=sk-abcdefghijklmnopQRSTUV",
                {"token": "token=supersecretvalue"},
            ],
        }
        encoded = json.dumps(redact(value))
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", encoded)
        self.assertNotIn("sk-abcdefghijklmnopQRSTUV", encoded)
        self.assertNotIn("supersecretvalue", encoded)
        self.assertIn("REDACTED", encoded)

    def test_sealed_package_round_trip_requires_independent_approval(self) -> None:
        task = self._tasks(1)[0]
        builder = assign_workers([task], 1)[0][1]
        reviewer = choose_reviewer(task, builder)
        proposal = ChangeProposal(
            summary="Add a bounded regression helper.",
            files=(
                ProposedFile(
                    "skeleton/example.py",
                    "def answer():\n    return 42\n",
                ),
            ),
            verification_notes=("CI must exercise the helper",),
        )
        review = ReviewDecision(
            True,
            "Small, scoped, and syntactically valid.",
        )
        package = {
            "version": 1,
            "status": "ready",
            "base_sha": "a" * 40,
            "planner": None,
            "entries": [
                entry_for(task, builder, reviewer, review, proposal)
            ],
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

    def test_sealed_package_rejects_same_builder_and_reviewer(self) -> None:
        task = self._tasks(1)[0]
        builder = assign_workers([task], 1)[0][1]
        proposal = ChangeProposal(
            summary="Add a bounded regression helper.",
            files=(ProposedFile("skeleton/example.py", "x = 1\n"),),
        )
        package = {
            "version": 1,
            "status": "ready",
            "base_sha": "b" * 40,
            "planner": None,
            "entries": [
                entry_for(
                    task,
                    builder,
                    builder,
                    ReviewDecision(True, "Not actually independent."),
                    proposal,
                )
            ],
        }
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "package.json"
            write_json(path, package)
            with self.assertRaises(ValueError):
                validate(path, self.config)


if __name__ == "__main__":
    unittest.main()
