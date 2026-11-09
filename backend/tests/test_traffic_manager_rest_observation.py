"""Actions queue observation must remain reliable under high run volume."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

# Backend quality executes tests with cwd=backend, while the traffic manager is
# a root-level package. Locate the trusted repository root explicitly.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from skeleton.automation import traffic_manager as manager


def _row(run_id: int, *, status: str = "queued") -> dict[str, object]:
    return {
        "databaseId": run_id,
        "name": "Repository Hygiene Gate",
        "event": "pull_request",
        "status": status,
        "conclusion": None,
        "headBranch": "feat/current",
        "headSha": "a" * 40,
        "createdAt": "2026-10-13T23:10:00Z",
        "updatedAt": "2026-10-13T23:10:01Z",
    }


def test_observation_uses_bounded_rest_projection_and_deduplicates(monkeypatch):
    requests: list[list[str]] = []

    def fake_gh_json(args: list[str]) -> list[dict[str, object]]:
        requests.append(args)
        assert args[0] == "api"
        assert args[2] == "--jq"
        assert "createdAt: .created_at" in args[3]
        assert "databaseId: .id" in args[3]
        if "?per_page=" in args[1]:
            return [_row(11), _row(12, status="completed")]
        if "status=queued" in args[1]:
            return [_row(11), _row(13)]
        return []

    monkeypatch.setattr(manager, "_gh_json", fake_gh_json)
    result = manager._observe_runs("Apeloff1/Skeleton")
    assert {run["databaseId"] for run in result} == {11, 12, 13}
    assert len(requests) == 1 + len(manager.ACTIVE_STATUSES)
    assert all("run" not in args[:2] for args in requests)
    assert all("per_page=100" in args[1] for args in requests)
    assert manager._timestamp(result[0]["createdAt"]) is not None


@pytest.mark.parametrize(
    "override",
    [
        {"databaseId": "invalid"},
        {"databaseId": 0},
        {"status": ""},
        {"createdAt": ""},
        {"updatedAt": None},
    ],
)
def test_malformed_run_fails_closed(monkeypatch, override):
    def fake_gh_json(args: list[str]):
        return [{**_row(1), **override}]

    monkeypatch.setattr(manager, "_gh_json", fake_gh_json)
    with pytest.raises(manager.TrafficManagerError, match="invalid Actions run"):
        manager._observe_runs("Apeloff1/Skeleton")


def test_failed_rest_history_does_not_assume_zero_pressure(monkeypatch):
    def fail_gh_json(args: list[str]):
        raise manager.TrafficManagerError("repository traffic observation failed")

    monkeypatch.setattr(manager, "_gh_json", fail_gh_json)
    with pytest.raises(manager.TrafficManagerError):
        manager._observe_runs("Apeloff1/Skeleton")


def test_rest_timestamps_retain_stale_queue_age():
    observed = int(datetime(2026, 10, 13, 23, 30, tzinfo=timezone.utc).timestamp())
    snapshot = manager.TrafficSnapshot(
        repository="Apeloff1/Skeleton",
        base_sha="b" * 40,
        observed_at=observed,
        current_run_id="",
        workflow_runs=(_row(9),),
        pull_requests=(),
        issues=(),
    )
    assert manager._queued_age_seconds(snapshot, snapshot.workflow_runs[0]) == 1200

def test_status_inventory_pages_beyond_100_queued_runs(monkeypatch):
    """Queue relief must see older runs hidden beyond GitHub's first page."""
    requests: list[str] = []

    def fake_gh_json(args: list[str]):
        url = args[1]
        requests.append(url)
        if "status=queued" in url and "&page=1" in url:
            return [_row(number) for number in range(1, 101)]
        if "status=queued" in url and "&page=2" in url:
            return [_row(number) for number in range(101, 183)]
        return []

    monkeypatch.setattr(manager, "_gh_json", fake_gh_json)
    rows = manager._observe_runs("Apeloff1/Skeleton")
    assert len(rows) == 182
    assert len({row["databaseId"] for row in rows}) == 182
    assert len([url for url in requests if "status=queued" in url]) == 2
    assert rows[-1]["databaseId"] == 182


def test_excessive_status_page_count_fails_closed(monkeypatch):
    """Never infer spare capacity from a truncated saturated inventory."""
    def fake_gh_json(args: list[str]):
        if "status=queued" in args[1]:
            return [_row(number) for number in range(1, 101)]
        return []

    monkeypatch.setattr(manager, "_gh_json", fake_gh_json)
    with pytest.raises(
        manager.TrafficManagerError,
        match="exceeded bounded active page limit",
    ):
        manager._observe_runs("Apeloff1/Skeleton")
