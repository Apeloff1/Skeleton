from __future__ import annotations

import json
import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.automation.automation_safety import (
    AutomationSafetyError,
    load_automation_safety,
)
from skeleton.automation.idle_studio import StudioConfig, run_studio
from skeleton.automation.idle_studio_v2 import propose


class AutomationSafetyTests(unittest.TestCase):
    def test_defaults_are_active(self) -> None:
        state = load_automation_safety({})
        self.assertFalse(state.blocked)
        self.assertEqual(state.status, "active")
        self.assertEqual(state.reason, "")

    def test_pause_and_quarantine_are_explicit_and_quarantine_wins_status(self) -> None:
        paused = load_automation_safety(
            {
                "SKELETON_AUTOMATION_PAUSED": "yes",
                "SKELETON_AUTOMATION_HOLD_REASON": "operator maintenance",
            }
        )
        self.assertTrue(paused.blocked)
        self.assertEqual(paused.status, "paused")
        self.assertEqual(paused.reason, "operator maintenance")

        quarantined = load_automation_safety(
            {
                "SKELETON_AUTOMATION_PAUSED": "true",
                "SKELETON_AUTOMATION_QUARANTINED": "1",
            }
        )
        self.assertTrue(quarantined.blocked)
        self.assertEqual(quarantined.status, "quarantined")

    def test_malformed_controls_fail_closed(self) -> None:
        with self.assertRaises(AutomationSafetyError):
            load_automation_safety({"SKELETON_AUTOMATION_PAUSED": "sometimes"})
        with self.assertRaises(AutomationSafetyError):
            load_automation_safety(
                {"SKELETON_AUTOMATION_QUARANTINED": "enabled-ish"}
            )
        with self.assertRaises(AutomationSafetyError):
            load_automation_safety(
                {"SKELETON_AUTOMATION_HOLD_REASON": "bad\x00reason"}
            )
        with self.assertRaises(AutomationSafetyError):
            load_automation_safety(
                {"SKELETON_AUTOMATION_HOLD_REASON": "x" * 501}
            )

    def test_idle_v2_pause_preempts_plan_and_model_requirements(self) -> None:
        config = StudioConfig(
            active_workers=4,
            tasks_per_run=1,
            max_model_calls=4,
            max_files_per_change=2,
            max_file_bytes=10_000,
            max_total_change_bytes=20_000,
            max_open_studio_prs=4,
            dry_run=True,
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state.json"
            package = root / "package.json"
            audit = root / "audit.jsonl"
            report = root / "report.md"
            state.write_text(
                json.dumps(
                    {
                        "base_sha": "a" * 40,
                        "runs": [],
                        "issues": [],
                        "pulls": [],
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "SKELETON_AUTOMATION_PAUSED": "true",
                    "SKELETON_AUTOMATION_HOLD_REASON": "maintenance",
                    "OPENAI_API_KEY": "must-not-be-consumed",
                },
                clear=False,
            ):
                self.assertEqual(
                    propose(state, package, audit, report, config),
                    0,
                )
                self.assertEqual(
                    os.environ.get("OPENAI_API_KEY"),
                    "must-not-be-consumed",
                )

            payload = json.loads(package.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "paused")
            self.assertEqual(payload["entries"], [])
            events = [
                json.loads(line)
                for line in audit.read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(
                any(
                    row.get("event") == "operator-safety-hold"
                    and row.get("status") == "paused"
                    for row in events
                )
            )

    def test_legacy_idle_pause_is_a_safe_noop_without_credentials(self) -> None:
        output = StringIO()
        with patch.dict(
            os.environ,
            {
                "SKELETON_AUTOMATION_PAUSED": "on",
                "SKELETON_AUTOMATION_HOLD_REASON": "incident response",
                "GITHUB_REPOSITORY": "",
                "GITHUB_TOKEN": "",
                "GH_TOKEN": "",
                "OPENAI_API_KEY": "",
                "GITHUB_SHA": "",
            },
            clear=False,
        ), redirect_stdout(output):
            self.assertEqual(run_studio(StudioConfig(dry_run=True)), 0)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "paused")
        self.assertEqual(payload["reason"], "incident response")

    def test_trusted_workflows_expose_repository_operator_controls(self) -> None:
        for path in (
            Path(".github/workflows/autonomous-studio.yml"),
            Path(".github/workflows/idle-studio.yml"),
        ):
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "SKELETON_AUTOMATION_PAUSED: ${{ vars.SKELETON_AUTOMATION_PAUSED }}",
                text,
            )
            self.assertIn(
                "SKELETON_AUTOMATION_QUARANTINED: ${{ vars.SKELETON_AUTOMATION_QUARANTINED }}",
                text,
            )
            self.assertIn(
                "SKELETON_AUTOMATION_HOLD_REASON: ${{ vars.SKELETON_AUTOMATION_HOLD_REASON }}",
                text,
            )


if __name__ == "__main__":
    unittest.main()
