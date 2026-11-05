"""Galaxy swarm planner API and real-build source authority fail closed."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core import databases
from core import swarm_scheduler as scheduler
from routes import swarm_planner as api


def test_missing_real_build_never_dispatches_phases(monkeypatch):
    class Collection:
        def find_one(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(databases, "get_sync_db", lambda: {"galaxy_builds": Collection()})
    monkeypatch.setattr(scheduler, "execute_schedule", lambda **_kw: (_ for _ in ()).throw(AssertionError("dispatched")))
    with pytest.raises(LookupError, match="not found"):
        scheduler.execute_build("missing", persist=False)


def test_build_authority_outage_never_dispatches(monkeypatch):
    monkeypatch.setattr(databases, "get_sync_db", lambda: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(scheduler, "execute_schedule", lambda **_kw: (_ for _ in ()).throw(AssertionError("dispatched")))
    with pytest.raises(RuntimeError, match="authority unavailable"):
        scheduler.execute_build("b", persist=False)


@pytest.mark.parametrize("inactive", [
    {"deleted": True},
    {"revoked": True},
    {"rights_revoked": True},
    {"state": "withdrawn"},
])
def test_inactive_build_cannot_run(monkeypatch, inactive):
    class Collection:
        def find_one(self, *_args, **_kwargs):
            return {"build_id": "b", **inactive}

    monkeypatch.setattr(databases, "get_sync_db", lambda: {"galaxy_builds": Collection()})
    monkeypatch.setattr(scheduler, "execute_schedule", lambda **_kw: (_ for _ in ()).throw(AssertionError("dispatched")))
    with pytest.raises(LookupError):
        scheduler.execute_build("b", persist=False)


def test_existing_source_build_dispatch_preserves_context(monkeypatch):
    seen = {}
    class Collection:
        def find_one(self, *_args, **_kwargs):
            return {"build_id": "b", "genre": "arcade", "subgenre": "puzzle", "title": "Example"}
    monkeypatch.setattr(databases, "get_sync_db", lambda: {"galaxy_builds": Collection()})
    def execute_schedule(**kwargs):
        seen.update(kwargs)
        return {"execution_complete": True}
    monkeypatch.setattr(scheduler, "execute_schedule", execute_schedule)
    assert scheduler.execute_build("b", persist=False)["execution_complete"] is True
    assert seen["game_ctx"]["genre"] == "arcade"
    assert seen["phases"] == scheduler.BUILD_STAGES
    assert seen["build_id"] == "b"


def test_real_build_route_maps_missing_to_404(monkeypatch):
    monkeypatch.setattr(scheduler, "execute_build", lambda **_kw: (_ for _ in ()).throw(LookupError("absent")))
    with pytest.raises(HTTPException) as error:
        api.execute_build(api.BuildReq(build_id="b"))
    assert error.value.status_code == 404


def test_real_build_route_maps_storage_failure_to_503(monkeypatch):
    monkeypatch.setattr(scheduler, "execute_build", lambda **_kw: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(HTTPException) as error:
        api.execute_build(api.BuildReq(build_id="b"))
    assert error.value.status_code == 503


def test_history_query_exposes_storage_error_as_503(monkeypatch):
    monkeypatch.setattr(scheduler, "get_runs", lambda *_a: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(HTTPException) as error:
        api.runs("b")
    assert error.value.status_code == 503


def test_invalid_plan_is_rejected_not_500(monkeypatch):
    with pytest.raises(HTTPException) as err:
        api.verify(api.VerifyReq(plan={"nodes": [{"id": "a"}], "edges": [], "waves": [{}]}))
    assert err.value.status_code == 422


def test_route_plan_diff_is_nonnegative_for_full_worker_replacement(monkeypatch):
    def fake_plan(*_args, **kwargs):
        workers = ("a", "b") if kwargs["seed"] == 1 else ("x", "y")
        return {
            "plan_hash": str(kwargs["seed"]),
            "nodes": [{"tier": "platoon", "phase_id": "p01", "workers": [
                {"code": code} for code in workers
            ]}],
        }
    monkeypatch.setattr(api.planner, "plan_build", fake_plan)
    output = api.plan_diff(phases=1, seed_a=1, seed_b=2)
    assert output["stability_pct"] == 0.0
    assert output["rows"][0]["similarity"] == 0.0


def test_out_of_bounds_plan_diff_count_returns_422():
    with pytest.raises(HTTPException) as err:
        api.plan_diff(phases=100_000)
    assert err.value.status_code == 422
