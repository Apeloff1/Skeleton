"""Swarm schedule persistence and comparison must provide truthful evidence."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core import swarm_scheduler as scheduler
from core import swarm_planner as planner
from core import databases


def _sample_run(hash_value: str, codes: list[str], seed: int = 3) -> dict:
    return {
        "build_id": "b",
        "plan_hash": hash_value,
        "seed": seed,
        "created_at": 123,
        "execution": {"waves": [{"rows": [{
            "phase_id": "a",
            "member_codes": codes,
        }]}]},
    }


def test_completely_replaced_cohort_cannot_report_negative_stability(monkeypatch):
    monkeypatch.setattr(
        scheduler, "get_runs",
        lambda *_args, **_kwargs: [_sample_run("a1", ["x", "y"]), _sample_run("b2", ["z", "w"])],
    )
    result = scheduler.diff_runs("b")
    assert result["stability_pct"] == 0.0
    assert result["rows"][0]["similarity"] == 0.0
    assert result["rows"][0]["added"] == ["w", "z"]


def test_partial_cohort_uses_bounded_weighted_intersection_over_union(monkeypatch):
    monkeypatch.setattr(
        scheduler, "get_runs",
        lambda *_args, **_kwargs: [_sample_run("a1", ["x", "y"]), _sample_run("b2", ["x", "z"])],
    )
    result = scheduler.diff_runs("b")
    assert result["stability_pct"] == pytest.approx(33.3)
    assert 0 <= result["stability_pct"] <= 100


def test_missing_requested_receipt_does_not_fallback_to_recent(monkeypatch):
    monkeypatch.setattr(
        scheduler, "get_runs",
        lambda *_args, **_kwargs: [_sample_run("a1", ["x"]), _sample_run("b2", ["y"])],
    )
    for kwargs in ({"hash_a": "missing"}, {"hash_b": "missing"}):
        result = scheduler.diff_runs("b", **kwargs)
        assert result["error"] == "requested plan receipt not found"
        assert "run_a" not in result


def test_selected_receipt_uses_actual_requested_hashes(monkeypatch):
    monkeypatch.setattr(
        scheduler, "get_runs",
        lambda *_args, **_kwargs: [_sample_run("a1", ["x"]), _sample_run("b2", ["y"])],
    )
    result = scheduler.diff_runs("b", hash_a="b2", hash_b="a1")
    assert result["run_a"]["plan_hash"] == "b2"
    assert result["run_b"]["plan_hash"] == "a1"


@pytest.mark.parametrize("limit", [0, -1, 101, True, 2.5, "3"])
def test_unbounded_or_invalid_history_limit_fails_before_db(monkeypatch, limit):
    monkeypatch.setattr(databases, "get_sync_db", lambda: (_ for _ in ()).throw(AssertionError("DB accessed")))
    with pytest.raises(ValueError):
        scheduler.get_runs("b", limit=limit)


def test_history_outage_is_not_reported_as_empty_results(monkeypatch):
    monkeypatch.setattr(databases, "get_sync_db", lambda: (_ for _ in ()).throw(ConnectionError("offline")))
    with pytest.raises(RuntimeError, match="history unavailable"):
        scheduler.get_runs("b")


def test_failed_receipt_insert_never_reports_success(monkeypatch):
    class Collection:
        def create_index(self, *args):
            return None
        def insert_one(self, row):
            raise OSError("storage full")

    monkeypatch.setattr(databases, "get_sync_db", lambda: {"swarm_schedule_runs": Collection()})
    with pytest.raises(RuntimeError, match="not durably recorded"):
        scheduler._persist_run({"build_id": "b", "plan_hash": "sha", "created_at": 123})


def test_unacknowledged_insert_never_reports_success(monkeypatch):
    class Collection:
        def create_index(self, *args):
            return None
        def insert_one(self, row):
            return SimpleNamespace(acknowledged=False)

    monkeypatch.setattr(databases, "get_sync_db", lambda: {"swarm_schedule_runs": Collection()})
    with pytest.raises(RuntimeError, match="not durably recorded"):
        scheduler._persist_run({"build_id": "b", "plan_hash": "sha", "created_at": 123})


def test_durable_insert_success_is_not_rejected_for_cleanup_failure(monkeypatch):
    class Collection:
        def create_index(self, *args):
            return None
        def insert_one(self, row):
            return SimpleNamespace(acknowledged=True)
        def estimated_document_count(self):
            raise OSError("retention check unavailable")

    monkeypatch.setattr(databases, "get_sync_db", lambda: {"swarm_schedule_runs": Collection()})
    scheduler._persist_run({"build_id": "b", "plan_hash": "sha", "created_at": 123})


def test_invalid_run_plan_does_not_start_any_phase():
    plan = planner.plan_build("b", phases=["a"], seed=3)
    plan["coverage"]["all_covered"] = False
    with pytest.raises(ValueError, match="unverified"):
        scheduler.run_with_executor(plan, lambda *_: (_ for _ in ()).throw(AssertionError("executed")))
