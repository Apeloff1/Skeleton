from __future__ import annotations

import json
from pathlib import Path

from skeleton.automation.chatgpt_adapter import ReasoningResult
from skeleton.automation.studio_director import _build_and_review, _changed_paths, _plan
from skeleton.automation.studio_registry import STUDIO_SIZE, select_cohort


class ScriptedReasoner:
    """Deterministic no-network stand-in for the Responses API adapter."""

    def __init__(self, *payloads: object) -> None:
        self._payloads = iter(payloads)
        self.calls = 0

    def reason(self, request: object) -> ReasoningResult:
        self.calls += 1
        try:
            payload = next(self._payloads)
        except StopIteration as exc:  # pragma: no cover - assertion aid
            raise AssertionError("unexpected extra model call") from exc
        return ReasoningResult(ok=True, text=json.dumps(payload))


def _safe_patch() -> str:
    path = "skeleton/automation/studio_report.py"
    return f"""diff --git a/{path} b/{path}
index 1111111..2222222 100644
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-old placeholder
+new placeholder
"""


def test_offline_studio_pipeline_smoke(tmp_path: Path) -> None:
    """Exercise planner -> builder -> independent reviewer without credentials."""

    assert STUDIO_SIZE == 1000
    cohort = select_cohort("smoke-run", size=15)
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text("- strengthen deterministic studio validation\n", encoding="utf-8")

    task_payload = {
        "tasks": [
            {
                "title": "Strengthen studio reporting",
                "objective": "Keep report rendering deterministic and reviewable.",
                "division": "testing",
                "paths": ["skeleton/automation/studio_report.py"],
            }
        ]
    }
    planner = ScriptedReasoner(task_payload)
    tasks = _plan(
        planner,
        cohort,
        max_tasks=1,
        backlog_path=backlog,
        repo_state_path=None,
    )

    assert planner.calls == 1
    assert len(tasks) == 1
    assert tasks[0].paths == ("skeleton/automation/studio_report.py",)

    patch = _safe_patch()
    builder_and_reviewer = ScriptedReasoner(
        {
            "patch": patch,
            "summary": "Keep the reporting path deterministic.",
            "tests": ["studio report focused suite"],
        },
        {
            "approve": True,
            "reasons": ["Patch remains within the planned source boundary."],
        },
    )
    reviewed = _build_and_review(builder_and_reviewer, tasks[0], seed="smoke-run")

    assert builder_and_reviewer.calls == 2
    assert reviewed is not None
    assert reviewed.builder.mode == "builder"
    assert reviewed.reviewer.mode == "reviewer"
    assert reviewed.builder.bot_id != reviewed.reviewer.bot_id
    assert _changed_paths(reviewed.patch) == tasks[0].paths


def test_offline_studio_pipeline_fails_closed_on_reviewer_rejection(tmp_path: Path) -> None:
    cohort = select_cohort("smoke-reject", size=9)
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text("- harden autonomous studio\n", encoding="utf-8")
    planner = ScriptedReasoner(
        {
            "tasks": [
                {
                    "title": "Review-only rejection path",
                    "objective": "Verify senior review remains authoritative.",
                    "division": "testing",
                    "paths": ["skeleton/automation/studio_report.py"],
                }
            ]
        }
    )
    task = _plan(planner, cohort, max_tasks=1, backlog_path=backlog)[0]
    reasoner = ScriptedReasoner(
        {
            "patch": _safe_patch(),
            "summary": "Candidate patch for rejection-path smoke coverage.",
            "tests": ["studio focused suite"],
        },
        {
            "approve": False,
            "reasons": ["Deliberate rejection for fail-closed smoke coverage."],
        },
    )

    assert _build_and_review(reasoner, task, seed="smoke-reject") is None
    assert reasoner.calls == 2
