from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import unittest
from unittest.mock import patch

from skeleton.automation.shift_manager import (
    IDLE_WORKFLOW,
    NIGHT_WORKFLOW,
    attendance,
    manager_plan,
    overtime,
    render_plan,
    secretary_delta,
)


class ShiftManagerTests(unittest.TestCase):
    def _run(
        self,
        *,
        run_id: int,
        name: str,
        status: str = "completed",
        conclusion: str = "success",
        minutes: int = 10,
    ) -> dict[str, object]:
        start = datetime(2026, 9, 16, 1, 0, tzinfo=timezone.utc)
        return {
            "databaseId": run_id,
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "startedAt": start.isoformat(),
            "updatedAt": (start + timedelta(minutes=minutes)).isoformat(),
            "displayTitle": f"run {run_id}",
            "url": f"https://example.test/actions/{run_id}",
        }

    def test_attendance_uses_latest_managed_run_as_authoritative_clock(self) -> None:
        runs = [
            self._run(run_id=1, name=NIGHT_WORKFLOW, status="completed"),
            {**self._run(run_id=2, name=NIGHT_WORKFLOW, status="in_progress"), "startedAt": "2026-09-16T02:00:00+00:00"},
            self._run(run_id=3, name=IDLE_WORKFLOW, status="completed"),
            self._run(run_id=4, name="Unrelated workflow", status="in_progress"),
        ]
        by_team = {row.team: row for row in attendance(runs)}
        self.assertEqual(by_team["night"].state, "clocked-in")
        self.assertEqual(by_team["night"].run_id, "2")
        self.assertEqual(by_team["idle"].state, "off")

    def test_overtime_records_duration_and_work_for_managed_teams_only(self) -> None:
        rows = overtime(
            [
                self._run(run_id=10, name=NIGHT_WORKFLOW, minutes=61),
                self._run(run_id=11, name=IDLE_WORKFLOW, minutes=36),
                self._run(run_id=12, name="Other", minutes=500),
            ]
        )
        self.assertEqual({row.run_id for row in rows}, {"10", "11"})
        idle = next(row for row in rows if row.team == "idle")
        self.assertEqual(idle.expected_minutes, 35)
        self.assertEqual(idle.work, "run 11")

    def test_secretary_fallback_deduplicates_and_ignores_bot_ledger_issues(self) -> None:
        state = {
            "runs": [self._run(run_id=20, name="Backend Quality", conclusion="failure")],
            "issues": [
                {"number": 1, "title": "security: validate boundary", "html_url": "https://example.test/issues/1"},
                {"number": 2, "title": "bot: idle studio ledger", "html_url": "https://example.test/issues/2"},
            ],
            "pulls": [{"number": 3, "title": "Blocked PR", "mergeable": "CONFLICTING"}],
        }
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            delta = secretary_delta(state)
        keys = [row["key"] for row in delta["workload"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("run:20", keys)
        self.assertIn("issue:1", keys)
        self.assertIn("pr:3", keys)
        self.assertNotIn("issue:2", keys)
        self.assertEqual(delta["status"], "deterministic-fallback")

    def test_manager_fallback_preserves_attendance_overtime_and_safety_invariants(self) -> None:
        state = {
            "runs": [
                self._run(run_id=30, name=NIGHT_WORKFLOW, status="in_progress", minutes=50),
                self._run(run_id=31, name=IDLE_WORKFLOW, minutes=40),
            ]
        }
        secretary = {
            "generated_at": "2026-09-16T03:00:00+00:00",
            "workload": [
                {
                    "key": "issue:99",
                    "team": "idle",
                    "title": "Fix regression",
                    "source": "https://example.test/issues/99",
                }
            ],
            "research_queue": [],
        }
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            plan = manager_plan(state, secretary)
        self.assertEqual(plan["status"], "deterministic-fallback")
        self.assertEqual(plan["refresh_minutes"], 30)
        self.assertEqual(plan["plan"]["delegations"][0]["task_key"], "issue:99")
        self.assertTrue(any("No direct main write" in item for item in plan["invariants"]))
        report = render_plan(plan)
        self.assertIn("SMB canonical shift plan", report)
        self.assertIn("issue:99", report)


if __name__ == "__main__":
    unittest.main()
