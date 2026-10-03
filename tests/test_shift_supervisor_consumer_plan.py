import base64
import gzip
import json
import hashlib
from datetime import datetime, timezone

import pytest

from core.shift_supervisor.consumer_plan import (
    CanonicalPlanError,
    consume_plan,
    decode_durable_state,
    normalize_worker_status,
)


def _body(plan_items):
    raw = json.dumps(
        {"version": 1, "plan_items": plan_items, "workers": [], "revisions": []},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.b64encode(gzip.compress(raw)).decode("ascii")
    return f"# Canonical\n\n<!-- SHIFT_SUPERVISOR_STATE\ngz:v1:{encoded}\n-->\n"


def _state(updated="2026-09-16T10:00:00Z"):
    return {
        "issues": [
            {
                "number": 42,
                "title": "[Shift Supervisor] Canonical Night + Idle Plan",
                "updated_at": updated,
                "body": _body(
                    [
                        {
                            "id": "idle-task-1",
                            "title": "Canonical idle task",
                            "description": "Implement only this task.",
                            "priority": 90,
                            "target_team": "idle",
                            "status": "queued",
                            "validation": ["focused regression"],
                        },
                        {
                            "id": "night-task-1",
                            "title": "Canonical night task",
                            "description": "Night work.",
                            "priority": 80,
                            "target_team": "night",
                            "status": "queued",
                        },
                    ]
                ),
            },
            {"number": 7, "title": "Ordinary issue", "body": "must not become idle work"},
        ],
        "runs": [
            {"id": 1, "status": "completed", "conclusion": "failure"},
            {"id": 2, "status": "in_progress", "conclusion": None},
        ],
        "pulls": [{"number": 9, "title": "ordinary PR"}],
        "base_sha": "abc",
    }


def test_idle_consumer_promotes_only_fresh_canonical_items():
    state, plan_map = consume_plan(
        _state(),
        team="idle",
        now=datetime(2026, 9, 16, 10, 10, tzinfo=timezone.utc),
        max_age_minutes=20,
    )

    supervisor = state["_shift_supervisor"]
    assert supervisor["status"] == "loaded"
    assert [item["id"] for item in supervisor["plan_items"]] == ["idle-task-1"]
    assert len(state["issues"]) == 1
    synthetic = state["issues"][0]
    assert "idle-task-1" in synthetic["title"]
    assert json.loads(synthetic["body"])["plan_item_id"] == "idle-task-1"
    assert state["pulls"] == []
    assert [run["id"] for run in state["runs"]] == [2]
    assert plan_map[f"issue:{synthetic['number']}"] == "idle-task-1"


def test_consumer_only_promotes_queued_items_with_completed_dependencies():
    state = _state()
    state["issues"][0]["body"] = _body(
        [
            {
                "id": "done-base",
                "title": "Completed dependency",
                "description": "Already done.",
                "priority": 50,
                "target_team": "night",
                "status": "done",
            },
            {
                "id": "eligible",
                "title": "Eligible follow-up",
                "description": "Dependency is complete.",
                "priority": 90,
                "target_team": "night",
                "status": "queued",
                "dependencies": ["done-base"],
            },
            {
                "id": "blocked",
                "title": "Blocked item",
                "description": "Must not execute.",
                "priority": 100,
                "target_team": "night",
                "status": "blocked",
            },
            {
                "id": "assigned",
                "title": "Already assigned",
                "description": "Must not be reclaimed.",
                "priority": 99,
                "target_team": "night",
                "status": "assigned",
            },
            {
                "id": "missing-dependency",
                "title": "Missing dependency",
                "description": "Must fail closed.",
                "priority": 98,
                "target_team": "night",
                "status": "queued",
                "dependencies": ["not-in-state"],
            },
        ]
    )

    consumed, _ = consume_plan(
        state,
        team="night",
        now=datetime(2026, 9, 16, 10, 10, tzinfo=timezone.utc),
        max_age_minutes=20,
    )

    assert [item["id"] for item in consumed["_shift_supervisor"]["plan_items"]] == ["eligible"]


def test_consumer_rejects_stale_generation():
    with pytest.raises(CanonicalPlanError, match="stale"):
        consume_plan(
            _state(),
            team="idle",
            now=datetime(2026, 9, 16, 10, 21, tzinfo=timezone.utc),
            max_age_minutes=20,
        )


def test_consumer_rejects_missing_canonical_issue():
    with pytest.raises(CanonicalPlanError, match="missing"):
        consume_plan(
            {"issues": [], "runs": [], "pulls": []},
            team="night",
            now=datetime(2026, 9, 16, 10, 5, tzinfo=timezone.utc),
        )


def test_normalize_worker_status_restores_canonical_plan_ids(tmp_path):
    status = tmp_path / "status.json"
    mapping = tmp_path / "map.json"
    status.write_text(
        json.dumps(
            {
                "workers": [
                    {
                        "worker_id": "idle-1",
                        "overtime_task_ids": ["issue:-7"],
                        "metadata": {
                            "worked_on": ["issue:-7"],
                            "last_task_id": "issue:-7",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    mapping.write_text(json.dumps({"issue:-7": "idle-task-1"}), encoding="utf-8")

    normalize_worker_status(status, mapping)

    payload = json.loads(status.read_text(encoding="utf-8"))
    worker = payload["workers"][0]
    assert worker["metadata"]["worked_on"] == ["idle-task-1"]
    assert worker["metadata"]["last_task_id"] == "idle-task-1"
    assert worker["overtime_task_ids"] == ["idle-task-1"]

def test_core_consumer_plan_module_delegates_to_canonical_cli():
    """The compatibility module must remain executable for workflow callers."""
    import runpy
    from unittest.mock import patch

    with patch(
        "skeleton.automation.shift_supervisor.consumer_plan.main",
        return_value=0,
    ) as canonical_main:
        with pytest.raises(SystemExit) as exc:
            runpy.run_module("core.shift_supervisor.consumer_plan", run_name="__main__")

    assert exc.value.code == 0
    canonical_main.assert_called_once_with()


def test_consumer_rejects_duplicate_canonical_plan_issues():
    state = _state()
    state["issues"].append(dict(state["issues"][0]))
    with pytest.raises(CanonicalPlanError, match="multiple canonical"):
        consume_plan(
            state,
            team="night",
            now=datetime(2026, 9, 16, 10, 10, tzinfo=timezone.utc),
        )


def test_consumer_rejects_duplicate_plan_item_ids():
    state = _state()
    state["issues"][0]["body"] = _body(
        [
            {
                "id": "duplicate",
                "title": "First",
                "description": "First task.",
                "target_team": "night",
                "status": "queued",
            },
            {
                "id": "duplicate",
                "title": "Second",
                "description": "Second task.",
                "target_team": "night",
                "status": "queued",
            },
        ]
    )
    with pytest.raises(CanonicalPlanError, match="duplicate plan item ids"):
        consume_plan(
            state,
            team="night",
            now=datetime(2026, 9, 16, 10, 10, tzinfo=timezone.utc),
        )


def test_prepare_state_replaces_state_atomically(tmp_path):
    from skeleton.automation.shift_supervisor.consumer_plan import prepare_state

    state_path = tmp_path / "repo-state.json"
    summary_path = tmp_path / "summary.md"
    state_path.write_text(json.dumps(_state()), encoding="utf-8")

    prepare_state(
        state_path,
        team="night",
        summary_path=summary_path,
        now=datetime(2026, 9, 16, 10, 10, tzinfo=timezone.utc),
    )

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["_shift_supervisor"]["status"] == "loaded"
    assert payload["_shift_supervisor"]["team"] == "night"
    assert summary_path.read_text(encoding="utf-8").startswith("## Shift supervisor")
    assert list(tmp_path.glob(".repo-state.json.*.tmp")) == []


def test_consumer_binds_loaded_plan_to_sha256_digest():
    state, _ = consume_plan(
        _state(),
        team="night",
        now=datetime(2026, 9, 16, 10, 10, tzinfo=timezone.utc),
    )
    supervisor = state["_shift_supervisor"]
    expected = hashlib.sha256(
        json.dumps(
            supervisor["plan_items"],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    assert supervisor["plan_digest_sha256"] == expected


def test_decode_durable_state_rejects_oversized_issue_body():
    with pytest.raises(CanonicalPlanError, match="issue body exceeds"):
        decode_durable_state("x" * 2_000_001)


def test_decode_durable_state_rejects_expansion_bomb():
    import base64
    import gzip

    expanded = b"x" * 5_000_001
    encoded = base64.b64encode(gzip.compress(expanded)).decode("ascii")
    body = f"<!-- SHIFT_SUPERVISOR_STATE\ngz:v1:{encoded}\n-->"
    with pytest.raises(CanonicalPlanError, match="expanded state exceeds"):
        decode_durable_state(body)


def test_plan_progress_distinguishes_drained_from_blocked():
    from skeleton.automation.shift_supervisor.consumer_plan import plan_progress

    drained = plan_progress(
        [
            {"id": "a", "target_team": "night", "status": "done"},
            {"id": "b", "target_team": "night", "status": "rejected"},
        ],
        "night",
    )
    assert drained["terminal"] is True
    assert drained["counts"]["done"] == 1
    blocked = plan_progress(
        [{"id": "a", "target_team": "night", "status": "blocked"}],
        "night",
    )
    assert blocked["terminal"] is False
    assert blocked["fingerprint_sha256"] != drained["fingerprint_sha256"]


def test_plan_progress_fingerprint_changes_when_status_advances():
    from skeleton.automation.shift_supervisor.consumer_plan import plan_progress

    queued = plan_progress([{"id": "a", "target_team": "night", "status": "queued"}], "night")
    done = plan_progress([{"id": "a", "target_team": "night", "status": "done"}], "night")
    assert queued["fingerprint_sha256"] != done["fingerprint_sha256"]

def test_compatibility_module_executes_canonical_prepare_cli(tmp_path):
    import os
    import subprocess
    import sys

    state_path = tmp_path / "repo-state.json"
    summary_path = tmp_path / "summary.md"
    state_path.write_text(json.dumps(_state()), encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(__import__("pathlib").Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "core.shift_supervisor.consumer_plan",
            "prepare",
            "--team",
            "night",
            "--state",
            str(state_path),
            "--summary",
            str(summary_path),
            "--max-age-minutes",
            "20",
            "--now",
            "2026-09-16T10:10:00+00:00",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["_shift_supervisor"]["status"] == "loaded"
    assert payload["_shift_supervisor"]["team"] == "night"
    assert [item["id"] for item in payload["_shift_supervisor"]["plan_items"]] == ["night-task-1"]
    assert "canonical plan loaded" in summary_path.read_text(encoding="utf-8")
