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
    canonical_idle_work_items,
    choose_reviewer,
    choose_squad,
    entry_for,
    plan_tasks,
    planner_evidence,
    propose,
    redact,
    research_task,
    validate,
    verify_proposal,
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

    def test_canonical_idle_items_ignore_competing_local_work(self) -> None:
        state = {
            "base_sha": "abc",
            "runs": [{"id": 9, "conclusion": "failure", "status": "completed", "name": "ci"}],
            "issues": [{"number": 7, "title": "Ordinary issue", "body": "must not become idle work"}],
            "pulls": [{"number": 3, "title": "review bait"}],
            "_shift_supervisor": {
                "status": "loaded",
                "team": "idle",
                "generation_id": "gen-idle-1",
                "plan_items": [
                    {
                        "id": "idle-task-1",
                        "title": "Canonical idle repair",
                        "description": "Implement only this supervisor item.",
                        "priority": 90,
                        "status": "queued",
                    },
                    {
                        "id": "done-task",
                        "title": "Already done",
                        "description": "Must not execute.",
                        "priority": 100,
                        "status": "done",
                    },
                ],
            },
        }
        tasks, generation = canonical_idle_work_items(state)
        self.assertEqual(generation, "gen-idle-1")
        self.assertEqual([task.key for task in tasks], ["idle-task-1"])
        self.assertIn("canonical-shift-supervisor", tasks[0].evidence)
        self.assertIn("gen-idle-1", tasks[0].evidence)

    def test_canonical_idle_items_fail_closed_without_supervisor_snapshot(self) -> None:
        with self.assertRaisesRegex(ValueError, "canonical shift-supervisor state was not loaded"):
            canonical_idle_work_items({"base_sha": "abc", "issues": [{"number": 1, "title": "x"}]})

    def test_researcher_rejects_patch_authorship(self) -> None:
        task = self._tasks(1)[0]
        builder = assign_workers([task], 1)[0][1]
        researcher = choose_squad(task, builder).researcher
        reasoner = _FakeReasoner(json.dumps({"findings": ["ok"], "patch": "diff --git a/x b/x"}))
        with self.assertRaises(ValueError):
            research_task(reasoner, task, researcher, ())

    def test_verifier_rejects_plan_state_mutation(self) -> None:
        task, squad, research, _review, _verification, proposal = self._approved_entry()
        review = ReviewDecision(True, "ok")
        reasoner = _FakeReasoner(
            json.dumps(
                {
                    "approve": True,
                    "reason": "ok",
                    "plan_items": [{"id": "rewritten"}],
                    "plan_generation": "hijack",
                }
            )
        )
        with self.assertRaises(ValueError):
            verify_proposal(reasoner, task, squad.verifier, proposal, research, review)

    def test_propose_consumes_canonical_plan_without_local_planner_or_state_mutation(self) -> None:
        import skeleton.automation.idle_studio_v2 as idle_studio_v2

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "state.json"
            package_path = root / "package.json"
            audit_path = root / "audit.jsonl"
            report_path = root / "report.md"
            state = {
                "base_sha": "d" * 40,
                "current_run_id": "run-1",
                "runs": [
                    {"id": 1, "status": "completed", "conclusion": "failure", "name": "ci"},
                ],
                "issues": [{"number": 44, "title": "Local issue must not be selected"}],
                "pulls": [],
                "_shift_supervisor": {
                    "status": "loaded",
                    "team": "idle",
                    "generation_id": "gen-live-9",
                    "plan_items": [
                        {
                            "id": "idle-task-9",
                            "title": "Canonical idle change",
                            "description": "Only this supervisor item is executable.",
                            "priority": 80,
                            "status": "queued",
                            "expected_output": "Bounded helper.",
                            "validation": ["focused unit test"],
                        }
                    ],
                },
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            original = state_path.read_bytes()
            payloads = [
                json.dumps({"findings": ["isolated helper"], "risks": [], "recommended_checks": ["unit"]}),
                json.dumps(
                    {
                        "summary": "Add a bounded helper.",
                        "files": [{"path": "skeleton/example.py", "content": "def answer():\n    return 42\n"}],
                        "verification": ["focused unit test"],
                    }
                ),
                json.dumps({"approve": True, "reason": "scoped", "risks": [], "verification": ["unit"]}),
                json.dumps({"approve": True, "reason": "ci can prove it", "required_checks": ["unit"]}),
            ]

            class RecordingReasoner(_FakeReasoner):
                def __init__(self, api_key="", model=None, timeout=45.0, scrub_environment=False) -> None:  # noqa: ANN001
                    super().__init__("")
                    import os
                    self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
                    self.payloads = list(payloads)
                    self.index = 0

                @staticmethod
                def redact(value: str) -> str:
                    return value

                def reason(self, request):  # noqa: ANN001
                    self.requests.append(request)
                    text = self.payloads[self.index]
                    self.index += 1
                    return ReasoningResult(True, text)

            previous = idle_studio_v2.ChatGPTReasoner
            idle_studio_v2.ChatGPTReasoner = RecordingReasoner  # type: ignore[misc,assignment]
            previous_key = None
            try:
                import os

                previous_key = os.environ.get("OPENAI_API_KEY")
                os.environ["OPENAI_API_KEY"] = "test-key"
                self.assertEqual(
                    propose(state_path, package_path, audit_path, report_path, self.config),
                    0,
                )
            finally:
                idle_studio_v2.ChatGPTReasoner = previous  # type: ignore[misc]
                import os

                if previous_key is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = previous_key

            self.assertEqual(state_path.read_bytes(), original)
            package = json.loads(package_path.read_text(encoding="utf-8"))
            self.assertEqual(package["status"], "ready")
            self.assertEqual(package["plan_source"], "shift-supervisor-canonical")
            self.assertEqual(package["plan_generation"], "gen-live-9")
            self.assertEqual(package["planner"]["task_keys"], ["idle-task-9"])
            self.assertEqual(package["planner"]["rationale"], "canonical-shift-supervisor")
            self.assertEqual(len(package["entries"]), 1)
            entry = package["entries"][0]
            self.assertEqual(entry["task"]["key"], "idle-task-9")
            self.assertEqual(entry["task"]["plan_item_id"], "idle-task-9")
            self.assertEqual(entry["task"]["plan_generation"], "gen-live-9")
            workers = {
                entry["researcher"]["worker_id"],
                entry["builder"]["worker_id"],
                entry["reviewer"]["worker_id"],
                entry["verifier"]["worker_id"],
            }
            self.assertEqual(len(workers), 4)
            events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(event.get("event") == "canonical-plan" for event in events))
            self.assertFalse(any(event.get("event") in {"planner", "planner-fallback"} for event in events))


if __name__ == "__main__":
    unittest.main()
