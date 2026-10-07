"""Pack H HTTP surface: pressure contract, idempotent records, outbox stats."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.api.pack_h import admit_pressure
from skeleton.api.pack_h import routes
from skeleton.api.pack_h.admit_pressure import PressureSnapshot, PressureState, RawPressure, classify
from skeleton.persistence.pack_h import IdempotencyStore, RecordStore


class FixedBoard:
    def __init__(self, snap: PressureSnapshot) -> None:
        self.snap = snap

    def snapshot(self, tenant_id=None):
        return self.snap


def _snap(state: PressureState, retry: float = 0.0, load: float = 0.1) -> PressureSnapshot:
    return PressureSnapshot(load=load, queue_depth=1, max_queue_depth=10, tenant_queue_depth=None,
                            retry_after_s=retry, state=state, observed_at=datetime.now(timezone.utc))


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(admit_pressure, "snapshot", lambda tenant_id=None: _snap(PressureState.OPEN))
    routes.install_services(routes.PackHServices(records=RecordStore(), idempotency=IdempotencyStore()))
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    yield TestClient(app), monkeypatch
    routes.install_services(None)


H = {"X-Tenant-Id": "t1"}


def test_pressure_open_is_200_without_retry_after(client):
    c, _ = client
    r = c.get("/api/v1/admit/pressure")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == 1 and body["state"] == "open"
    assert "retry-after" not in r.headers
    assert r.headers["cache-control"] == "no-store"
    assert PressureSnapshot.from_dict(body).state is PressureState.OPEN


def test_pressure_shed_is_503_with_retry_after(client):
    c, mp = client
    mp.setattr(admit_pressure, "snapshot", lambda tenant_id=None: _snap(PressureState.SHED, 2.31, 0.97))
    r = c.get("/api/v1/admit/pressure/t1")
    assert r.status_code == 503
    assert r.headers["retry-after"] == "3"
    assert r.json()["retry_after_s"] == 2.31


def test_pressure_rejects_bad_tenant(client):
    c, _ = client
    assert c.get("/api/v1/admit/pressure/bad tenant!").status_code == 400


def test_classify_thresholds():
    def raw(queued, active=0, **kw):
        return RawPressure(active=active, queued=queued, max_concurrency=10, max_queue_depth=100, **kw)

    assert classify(raw(10)).state is PressureState.OPEN
    t = classify(raw(80))
    assert t.state is PressureState.THROTTLE and t.retry_after_s > 0
    assert classify(raw(96)).state is PressureState.SHED
    full = classify(raw(100))
    assert full.state is PressureState.SHED and full.reason == "queue_full"
    tenant = classify(raw(1, tenant_id="t", tenant_queued=5, max_tenant_queue_depth=5))
    assert tenant.state is PressureState.SHED and tenant.tenant_queue_depth == 5


def test_create_requires_key_and_tenant(client):
    c, _ = client
    assert c.post("/api/v1/pack-h/records", json={"kind": "note"}, headers=H).json()["error"] == \
        "idempotency_key_required"
    assert c.post("/api/v1/pack-h/records", json={"kind": "note"},
                  headers={"Idempotency-Key": "key-00001"}).status_code == 400
    assert c.post("/api/v1/pack-h/records", json={"kind": "note"},
                  headers={**H, "Idempotency-Key": "bad"}).json()["error"] == "idempotency_key_invalid"


def test_create_replays_and_rejects_mismatch(client):
    c, _ = client
    h = {**H, "Idempotency-Key": "key-create-1"}
    payload = {"kind": "note", "body": {"t": 1}}
    r1 = c.post("/api/v1/pack-h/records", json=payload, headers=h)
    assert r1.status_code == 201
    r2 = c.post("/api/v1/pack-h/records", json=payload, headers=h)
    assert r2.status_code == 201
    assert r2.headers["idempotent-replayed"] == "true"
    assert r2.json() == r1.json()
    r3 = c.post("/api/v1/pack-h/records", json={"kind": "note", "body": {"t": 2}}, headers=h)
    assert r3.status_code == 422 and r3.json()["error"] == "idempotency_key_mismatch"
    listed = c.get("/api/v1/pack-h/records", headers=H).json()["items"]
    assert len(listed) == 1
    assert c.get("/api/v1/pack-h/outbox/stats").json()["ready"] == 1


def test_update_with_if_match_and_delete(client):
    c, _ = client
    rid = c.post("/api/v1/pack-h/records", json={"kind": "note", "record_id": "r1"},
                 headers={**H, "Idempotency-Key": "key-c-0001"}).json()["record_id"]
    g = c.get(f"/api/v1/pack-h/records/{rid}", headers=H)
    assert g.headers["etag"] == '"1"'
    stale = c.put(f"/api/v1/pack-h/records/{rid}", json={"body": {"x": 1}},
                  headers={**H, "If-Match": '"7"', "Idempotency-Key": "key-u-0001"})
    assert stale.status_code == 412 and stale.json()["current_version"] == 1
    ok = c.put(f"/api/v1/pack-h/records/{rid}", json={"body": {"x": 1}},
               headers={**H, "If-Match": '"1"', "Idempotency-Key": "key-u-0002"})
    assert ok.status_code == 200 and ok.json()["version"] == 2
    d = c.delete(f"/api/v1/pack-h/records/{rid}", headers={**H, "Idempotency-Key": "key-d-0001"})
    assert d.status_code == 200
    assert c.get(f"/api/v1/pack-h/records/{rid}", headers=H).status_code == 404
    assert c.get("/api/v1/pack-h/outbox/stats").json()["ready"] == 3


def test_tenants_are_isolated(client):
    c, _ = client
    c.post("/api/v1/pack-h/records", json={"kind": "note", "record_id": "r1"},
           headers={**H, "Idempotency-Key": "key-iso-001"})
    assert c.get("/api/v1/pack-h/records/r1", headers={"X-Tenant-Id": "t2"}).status_code == 404


def test_writes_shed_under_pressure(client):
    c, mp = client
    mp.setattr(admit_pressure, "snapshot", lambda tenant_id=None: _snap(PressureState.SHED, 1.5, 0.99))
    r = c.post("/api/v1/pack-h/records", json={"kind": "note"}, headers={**H, "Idempotency-Key": "key-shed-01"})
    assert r.status_code == 503 and r.headers["retry-after"] == "2"


def test_invalid_record_is_422_and_stored_for_replay(client):
    c, _ = client
    h = {**H, "Idempotency-Key": "key-bad-001"}
    r1 = c.post("/api/v1/pack-h/records", json={"kind": "Bad Kind"}, headers=h)
    assert r1.status_code == 422
    r2 = c.post("/api/v1/pack-h/records", json={"kind": "Bad Kind"}, headers=h)
    assert r2.headers.get("idempotent-replayed") == "true"
