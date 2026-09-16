from __future__ import annotations

from skeleton.automation.studio_report import render_report


def test_report_explains_planned_accepted_and_rejected_work() -> None:
    rows = [
        {
            "ts": "2026-01-01T00:00:00+00:00",
            "run_id": "7",
            "event": "run_started",
            "studio_size": 1000,
            "cohort": [{"bot_id": "studio-0001"}],
        },
        {
            "ts": "2026-01-01T00:01:00+00:00",
            "run_id": "7",
            "event": "plan_created",
            "tasks": [
                {
                    "title": "Mechanics",
                    "objective": "Improve deterministic mechanics.",
                    "division": "gameplay_systems",
                    "paths": ["skeleton/gameplay/core.py"],
                }
            ],
        },
        {
            "ts": "2026-01-01T00:02:00+00:00",
            "run_id": "7",
            "event": "patch_accepted",
            "task": "Mechanics",
            "builder": "studio-0100",
            "reviewer": "studio-0103",
            "summary": "Improved mechanics.",
            "review_reasons": ["bounded and testable"],
        },
        {
            "ts": "2026-01-01T00:03:00+00:00",
            "run_id": "7",
            "event": "run_finished",
        },
    ]

    report = render_report(rows)

    assert "Registered virtual workers: **1000**" in report
    assert "Mechanics" in report
    assert "studio-0100" in report
    assert "Safety boundary" in report


def test_report_surfaces_run_level_planning_failure() -> None:
    rows = [
        {
            "ts": "2026-01-01T00:00:00+00:00",
            "run_id": "8",
            "event": "run_started",
            "studio_size": 1000,
            "cohort": [{"bot_id": "studio-0001"}],
        },
        {
            "ts": "2026-01-01T00:00:01+00:00",
            "run_id": "8",
            "event": "run_failed_closed",
            "stage": "planning",
            "error": "model call failed closed: missing_api_key",
            "status": "failed_closed",
        },
    ]

    report = render_report(rows)

    assert "Rejected/failed-closed tasks or runs: **1**" in report
    assert "planning" in report
    assert "missing_api_key" in report
    assert "`run_failed_closed`: 1" in report
