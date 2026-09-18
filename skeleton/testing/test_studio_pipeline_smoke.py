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


def _research_payload() -> dict[str, object]:
    return {
        "findings": ["The planned reporting path is isolated and deterministic."],
        "risks": ["A patch outside the planned path must fail closed."],
        "recommended_checks": ["studio report focused suite"],
    }


def _verification_payload() -> dict[str, object]:
    return {
        "approve": True,
        "reasons": ["Patch and review evidence satisfy the planned boundary."],
        "required_checks": ["studio report focused suite"],
    }


def test_offline_studio_pipeline_smoke(tmp_path: Path) -> None:
    """Exercise planner -> scout -> builder -> reviewer -> tester offline."""

    assert STUDIO_SIZE == 1000
    cohort = select_cohort("smoke-run", size=15)
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text("- strengthen deterministic studio validation\n", encoding="utf-8")

    task_payload = {
        "tasks": [
            {
                "title": "Strengthen studio reporting",
                "objective": "Keep report rendering deterministic and reviewable.",
                "division": "qa_verification",
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
    squad_reasoner = ScriptedReasoner(
        _research_payload(),
        {
            "patch": patch,
            "summary": "Keep the reporting path deterministic.",
            "tests": ["studio report focused suite"],
        },
        {
            "approve": True,
            "reasons": ["Patch remains within the planned source boundary."],
        },
        _verification_payload(),
    )
    reviewed = _build_and_review(squad_reasoner, tasks[0], seed="smoke-run")

    assert squad_reasoner.calls == 4
    assert reviewed is not None
    assert reviewed.researcher.mode == "scout"
    assert reviewed.builder.mode == "builder"
    assert reviewed.reviewer.mode == "reviewer"
    assert reviewed.verifier.mode == "tester"
    assert len(
        {
            reviewed.researcher.bot_id,
            reviewed.builder.bot_id,
            reviewed.reviewer.bot_id,
            reviewed.verifier.bot_id,
        }
    ) == 4
    assert reviewed.required_checks == ("studio report focused suite",)
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
                    "objective": "Verify adversarial review remains authoritative.",
                    "division": "qa_verification",
                    "paths": ["skeleton/automation/studio_report.py"],
                }
            ]
        }
    )
    task = _plan(planner, cohort, max_tasks=1, backlog_path=backlog)[0]
    reasoner = ScriptedReasoner(
        _research_payload(),
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
    assert reasoner.calls == 3
