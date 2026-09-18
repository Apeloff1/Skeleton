from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

MAX_PROJECT_CONTEXT_BYTES = 64_000
MAX_PLANNING_ISSUES = 12
MAX_OPEN_PULL_REQUESTS = 12
MAX_WORKFLOW_RUNS = 16
MAX_CODE_SCANNING_ALERTS = 8
MAX_WORKER_SNAPSHOTS = 48

_STATUS_TITLES = frozenset(
    {
        "[Shift Supervisor] Idle Worker Status",
        "[Shift Supervisor] Night Worker Status",
    }
)


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _labels(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result: list[str] = []
    for item in value[:8]:
        if isinstance(item, Mapping):
            name = _text(item.get("name"), 80)
        else:
            name = _text(item, 80)
        if name:
            result.append(name)
    return result


def _newest(rows: Sequence[Any], limit: int) -> list[Mapping[str, Any]]:
    mapped = [row for row in rows if isinstance(row, Mapping)]
    return sorted(
        mapped,
        key=lambda row: _text(row.get("updatedAt") or row.get("createdAt"), 64),
        reverse=True,
    )[:limit]


def _compact_issue(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "number": row.get("number"),
        "title": _text(row.get("title"), 240),
        "body": _text(row.get("body"), 700),
        "labels": _labels(row.get("labels")),
        "updatedAt": _text(row.get("updatedAt"), 64),
        "url": _text(row.get("url"), 320),
    }


def _compact_pull(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "number": row.get("number"),
        "title": _text(row.get("title"), 240),
        "body": _text(row.get("body"), 800),
        "labels": _labels(row.get("labels")),
        "headRefName": _text(row.get("headRefName"), 160),
        "baseRefName": _text(row.get("baseRefName"), 160),
        "updatedAt": _text(row.get("updatedAt"), 64),
        "url": _text(row.get("url"), 320),
    }


def _compact_run(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "databaseId": row.get("databaseId"),
        "name": _text(row.get("name"), 180),
        "status": _text(row.get("status"), 40),
        "conclusion": _text(row.get("conclusion"), 40),
        "headBranch": _text(row.get("headBranch"), 160),
        "headSha": _text(row.get("headSha"), 64),
        "createdAt": _text(row.get("createdAt"), 64),
        "url": _text(row.get("url"), 320),
    }


def _compact_alert(row: Mapping[str, Any]) -> dict[str, Any]:
    rule = _mapping(row.get("rule"))
    tool = _mapping(row.get("tool"))
    most_recent = _mapping(row.get("most_recent_instance"))
    location = _mapping(most_recent.get("location"))
    return {
        "number": row.get("number"),
        "state": _text(row.get("state"), 40),
        "rule": {
            "id": _text(rule.get("id"), 160),
            "name": _text(rule.get("name"), 200),
            "severity": _text(rule.get("security_severity_level"), 40),
        },
        "tool": {"name": _text(tool.get("name"), 160)},
        "path": _text(location.get("path"), 320),
        "created_at": _text(row.get("created_at"), 64),
        "html_url": _text(row.get("html_url"), 320),
    }


def _compact_worker(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _mapping(row.get("metadata"))
    worked_on = metadata.get("worked_on")
    if not isinstance(worked_on, list):
        worked_on = []
    overtime_tasks = row.get("overtime_task_ids")
    if not isinstance(overtime_tasks, list):
        overtime_tasks = []
    return {
        "worker_id": _text(row.get("worker_id"), 120),
        "team": _text(row.get("team"), 20),
        "status": _text(row.get("status"), 20),
        "clocked_in_at": _text(row.get("clocked_in_at"), 64),
        "clocked_out_at": _text(row.get("clocked_out_at"), 64),
        "last_heartbeat_at": _text(row.get("last_heartbeat_at"), 64),
        "current_task_id": _text(row.get("current_task_id"), 160) or None,
        "normal_shift_minutes": row.get("normal_shift_minutes", 0),
        "overtime_minutes": row.get("overtime_minutes", 0),
        "overtime_task_ids": [_text(value, 160) for value in overtime_tasks[:12]],
        "metadata": {
            "shift_key": _text(metadata.get("shift_key"), 160),
            "shift_minutes": metadata.get("shift_minutes", 0),
            "worked_on": [_text(value, 160) for value in worked_on[:12]],
        },
    }


def _extract_worker_snapshots(issues: Sequence[Any]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for item in issues:
        if not isinstance(item, Mapping):
            continue
        if _text(item.get("title"), 300) not in _STATUS_TITLES:
            continue
        try:
            payload = json.loads(str(item.get("body", "{}")))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("version") != 1:
            continue
        workers = payload.get("workers", [])
        if not isinstance(workers, list):
            continue
        for worker in workers:
            if isinstance(worker, Mapping):
                compact = _compact_worker(worker)
                if compact["worker_id"] and compact["team"] in {"night", "idle"}:
                    snapshots.append(compact)
                    if len(snapshots) >= MAX_WORKER_SNAPSHOTS:
                        return snapshots
    return snapshots


def build_bounded_project_context(
    *,
    repository: str,
    base_sha: str,
    issues: Sequence[Any],
    pulls: Sequence[Any],
    workflow_runs: Sequence[Any],
    code_scanning_alerts: Sequence[Any],
    plan_title: str,
) -> dict[str, Any]:
    """Build the supervisor model snapshot under a hard serialized size budget."""

    planning_source = [
        item
        for item in issues
        if isinstance(item, Mapping)
        and _text(item.get("title"), 300) not in _STATUS_TITLES
        and _text(item.get("title"), 300) != plan_title
    ]
    context: dict[str, Any] = {
        "repository": _text(repository, 240),
        "base_sha": _text(base_sha, 80),
        "open_issues": [
            _compact_issue(row)
            for row in _newest(planning_source, MAX_PLANNING_ISSUES)
        ],
        "open_pull_requests": [
            _compact_pull(row)
            for row in _newest(pulls, MAX_OPEN_PULL_REQUESTS)
        ],
        "workflow_runs": [
            _compact_run(row)
            for row in _newest(workflow_runs, MAX_WORKFLOW_RUNS)
        ],
        "code_scanning_alerts": [
            _compact_alert(row)
            for row in _newest(code_scanning_alerts, MAX_CODE_SCANNING_ALERTS)
        ],
        "worker_snapshots": _extract_worker_snapshots(issues),
        "research_policy": {
            "sources": [
                "github-issues",
                "github-pull-requests",
                "github-actions",
                "code-scanning",
                "hosted-web-search",
            ],
            "external_evidence_is_untrusted": True,
            "objective": (
                "produce executable, validated work for the night and idle engineering teams"
            ),
        },
        "snapshot_budget": {
            "max_serialized_bytes": MAX_PROJECT_CONTEXT_BYTES,
            "issues": MAX_PLANNING_ISSUES,
            "pull_requests": MAX_OPEN_PULL_REQUESTS,
            "workflow_runs": MAX_WORKFLOW_RUNS,
            "code_scanning_alerts": MAX_CODE_SCANNING_ALERTS,
            "worker_snapshots": MAX_WORKER_SNAPSHOTS,
            "serialized_bytes": 0,
        },
    }

    def serialized_size() -> int:
        return len(
            json.dumps(
                context,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        )

    if serialized_size() > MAX_PROJECT_CONTEXT_BYTES:
        # Bodies are the least structured/highest-volume fields. Remove them
        # before dropping current evidence or staffing state.
        for row in context["open_issues"]:
            row["body"] = _text(row.get("body"), 200)
        for row in context["open_pull_requests"]:
            row["body"] = _text(row.get("body"), 240)
    if serialized_size() > MAX_PROJECT_CONTEXT_BYTES:
        context["workflow_runs"] = context["workflow_runs"][:8]
        context["code_scanning_alerts"] = context["code_scanning_alerts"][:4]
        context["worker_snapshots"] = context["worker_snapshots"][:24]

    for _ in range(3):
        context["snapshot_budget"]["serialized_bytes"] = serialized_size()

    final_size = serialized_size()
    context["snapshot_budget"]["serialized_bytes"] = final_size
    if serialized_size() > MAX_PROJECT_CONTEXT_BYTES:
        raise ValueError("bounded shift-supervisor project context exceeds byte budget")

    return context
