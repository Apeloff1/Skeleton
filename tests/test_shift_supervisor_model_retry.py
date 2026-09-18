from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message
from unittest.mock import patch

import pytest

from core.shift_supervisor.context_budget import (
    MAX_PROJECT_CONTEXT_BYTES,
    build_bounded_project_context,
)
from core.shift_supervisor.model_gateway import ModelGateway, ModelRequestError


def _http_error(*, code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://example.invalid", code, "error", headers, None)


def test_429_honors_retry_after_with_upper_bound() -> None:
    gateway = ModelGateway(max_retry_delay_seconds=30)

    assert gateway._retry_delay(_http_error(code=429, retry_after="12"), 1) == 12
    assert gateway._retry_delay(_http_error(code=429, retry_after="120"), 1) == 30


def test_invalid_or_unrelated_retry_after_uses_bounded_backoff() -> None:
    gateway = ModelGateway(max_retry_delay_seconds=30)

    assert gateway._retry_delay(_http_error(code=429, retry_after="later"), 2) == 2
    assert gateway._retry_delay(_http_error(code=503, retry_after="20"), 3) == 4


def test_rate_limit_can_use_extended_bounded_retry_budget(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-key")
    monkeypatch.delenv("SHIFT_MODEL_API_URL", raising=False)
    gateway = ModelGateway(max_attempts=6, max_non_rate_limit_attempts=3)
    calls = 0

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        assert timeout == gateway.timeout_seconds
        if calls <= 3:
            raise _http_error(code=429, retry_after="0")
        return io.BytesIO(json.dumps({"output_text": '{"ok": true}'}).encode("utf-8"))

    with patch("urllib.request.urlopen", fake_urlopen), patch("time.sleep") as sleep:
        result = gateway.call_json(
            system_prompt="system",
            user_prompt="user",
            correlation_id="corr-rate-limit",
        )

    assert result == {"ok": True}
    assert calls == 4
    assert sleep.call_count == 3


def test_non_rate_limit_failures_keep_standard_retry_budget(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-key")
    monkeypatch.delenv("SHIFT_MODEL_API_URL", raising=False)
    gateway = ModelGateway(max_attempts=6, max_non_rate_limit_attempts=3)
    calls = 0

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        assert timeout == gateway.timeout_seconds
        raise _http_error(code=503, retry_after="0")

    with patch("urllib.request.urlopen", fake_urlopen), patch("time.sleep") as sleep:
        with pytest.raises(ModelRequestError, match="after 3 attempts"):
            gateway.call_json(
                system_prompt="system",
                user_prompt="user",
                correlation_id="corr-standard-failure",
            )

    assert calls == 3
    assert sleep.call_count == 2


def test_project_context_is_hard_bounded_and_prefers_recent_evidence() -> None:
    issues = [
        {
            "number": index,
            "title": f"issue-{index}",
            "body": "i" * 20_000,
            "labels": [{"name": "reliability"}],
            "updatedAt": f"2026-09-{index + 1:02d}T00:00:00Z",
            "url": f"https://example.invalid/issues/{index}",
        }
        for index in range(24)
    ]
    issues.append(
        {
            "number": 900,
            "title": "[Shift Supervisor] Canonical Night + Idle Plan",
            "body": "p" * 20_000,
            "updatedAt": "2026-09-30T00:00:00Z",
            "url": "https://example.invalid/issues/900",
        }
    )
    workers = [
        {
            "worker_id": f"worker-{index}",
            "team": "night" if index % 2 else "idle",
            "status": "idle",
            "current_task_id": None,
            "normal_shift_minutes": 10,
            "overtime_minutes": 0,
            "overtime_task_ids": [],
            "metadata": {
                "shift_key": f"shift-{index}",
                "shift_minutes": 10,
                "worked_on": [f"task-{index}"],
                "unbounded_noise": "x" * 10_000,
            },
        }
        for index in range(80)
    ]
    issues.append(
        {
            "number": 901,
            "title": "[Shift Supervisor] Night Worker Status",
            "body": json.dumps({"version": 1, "workers": workers}),
            "updatedAt": "2026-09-30T00:00:00Z",
            "url": "https://example.invalid/issues/901",
        }
    )
    pulls = [
        {
            "number": index,
            "title": f"pr-{index}",
            "body": "p" * 20_000,
            "labels": [{"name": "ci"}],
            "headRefName": f"branch-{index}",
            "baseRefName": "main",
            "updatedAt": f"2026-09-{index + 1:02d}T00:00:00Z",
            "url": f"https://example.invalid/pulls/{index}",
        }
        for index in range(24)
    ]
    runs = [
        {
            "databaseId": index,
            "name": f"run-{index}",
            "status": "completed",
            "conclusion": "success",
            "headBranch": "main",
            "headSha": f"{index:040d}",
            "createdAt": f"2026-09-{index + 1:02d}T00:00:00Z",
            "url": f"https://example.invalid/runs/{index}",
        }
        for index in range(24)
    ]
    alerts = [
        {
            "number": index,
            "state": "open",
            "rule": {
                "id": f"rule-{index}",
                "name": "security finding",
                "security_severity_level": "high",
            },
            "tool": {"name": "scanner"},
            "most_recent_instance": {"location": {"path": f"src/{index}.py"}},
            "created_at": f"2026-09-{index + 1:02d}T00:00:00Z",
            "html_url": f"https://example.invalid/alerts/{index}",
        }
        for index in range(16)
    ]

    context = build_bounded_project_context(
        repository="Apeloff1/Skeleton",
        base_sha="a" * 40,
        issues=issues,
        pulls=pulls,
        workflow_runs=runs,
        code_scanning_alerts=alerts,
        plan_title="[Shift Supervisor] Canonical Night + Idle Plan",
    )
    encoded = json.dumps(
        context,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    assert len(encoded) <= MAX_PROJECT_CONTEXT_BYTES
    assert len(context["open_issues"]) == 12
    assert len(context["open_pull_requests"]) == 12
    assert len(context["workflow_runs"]) == 16
    assert len(context["code_scanning_alerts"]) == 8
    assert len(context["worker_snapshots"]) == 48
    assert context["open_issues"][0]["number"] == 23
    assert context["open_pull_requests"][0]["number"] == 23
    assert all(len(row["body"]) <= 700 for row in context["open_issues"])
    assert all(len(row["body"]) <= 800 for row in context["open_pull_requests"])
    assert not any(
        row["title"] == "[Shift Supervisor] Canonical Night + Idle Plan"
        for row in context["open_issues"]
    )
    assert "unbounded_noise" not in context["worker_snapshots"][0]["metadata"]


def test_project_context_budget_metadata_reports_pre_metadata_size() -> None:
    context = build_bounded_project_context(
        repository="Apeloff1/Skeleton",
        base_sha="b" * 40,
        issues=[],
        pulls=[],
        workflow_runs=[],
        code_scanning_alerts=[],
        plan_title="[Shift Supervisor] Canonical Night + Idle Plan",
    )

    assert 0 < context["snapshot_budget"]["serialized_bytes"] < MAX_PROJECT_CONTEXT_BYTES
