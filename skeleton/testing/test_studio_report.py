from __future__ import annotations

import pytest

from skeleton.automation.studio_report import load_records, render_report, verify_audit_chain


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


def test_report_rejects_mixed_run_ids() -> None:
    rows = [
        {"ts": "2026-01-01T00:00:00+00:00", "run_id": "a", "event": "run_started"},
        {"ts": "2026-01-01T00:00:01+00:00", "run_id": "b", "event": "run_finished"},
    ]
    with pytest.raises(ValueError, match="multiple run ids"):
        render_report(rows)


def test_report_marks_missing_terminal_record() -> None:
    report = render_report(
        [{"ts": "2026-01-01T00:00:00+00:00", "run_id": "9", "event": "run_started"}]
    )
    assert "Audit lifecycle: **incomplete/ambiguous** (0 terminal records)" in report


def test_audit_chain_rejects_mutated_record():
    import hashlib
    import json

    rows = []
    previous = "0" * 64
    for sequence, event in enumerate(("run_started", "run_finished"), start=1):
        row = {
            "ts": f"2026-01-01T00:00:0{sequence}+00:00",
            "run_id": "chain",
            "event": event,
            "sequence": sequence,
            "previous_record_sha256": previous,
        }
        canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
        row["record_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        previous = row["record_sha256"]
        rows.append(row)
    rows[0]["event"] = "tampered"
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_audit_chain(rows)


def test_audit_chain_rejects_reordered_records():
    import hashlib
    import json

    rows = []
    previous = "0" * 64
    for sequence, event in enumerate(("run_started", "run_finished"), start=1):
        row = {
            "ts": f"2026-01-01T00:00:0{sequence}+00:00",
            "run_id": "chain",
            "event": event,
            "sequence": sequence,
            "previous_record_sha256": previous,
        }
        canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
        row["record_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        previous = row["record_sha256"]
        rows.append(row)
    with pytest.raises(ValueError, match="sequence is discontinuous"):
        verify_audit_chain(list(reversed(rows)))


def test_load_records_rejects_symlink(tmp_path):
    target = tmp_path / "real.jsonl"
    target.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "audit.jsonl"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(ValueError, match="symlink"):
        load_records(link)


def test_load_records_rejects_oversized_audit(tmp_path):
    path = tmp_path / "audit.jsonl"
    path.write_bytes(b"x" * 10_000_001)
    with pytest.raises(ValueError, match="exceeds 10 MB"):
        load_records(path)
