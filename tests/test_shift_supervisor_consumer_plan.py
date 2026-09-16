import base64
import gzip
import json
from datetime import datetime, timezone

import pytest

from core.shift_supervisor.consumer_plan import (
    CanonicalPlanError,
    consume_plan,
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
