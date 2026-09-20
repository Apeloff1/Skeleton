"""HTTP route tests for standalone OmniFabric router (no server lifespan)."""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.api import omnifabric_routes
from skeleton.kernel.omnifabric.service import OmniFabricService


@pytest.fixture()
def client():
    omnifabric_routes.set_omnifabric_service(OmniFabricService(hot_cap=128))
    app = FastAPI()
    app.include_router(omnifabric_routes.router)
    with TestClient(app) as c:
        yield c
    omnifabric_routes.set_omnifabric_service(None)


def test_meta(client):
    r = client.get("/omnifabric/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["surface"] == "OmniFabric"
    assert "gameforge-rs" in body["sibling"]



def test_append_verify_tail_status_0(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_0",
        "kind": "decide",
        "payload": {"n": 0},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_0"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_0", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_1(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_1",
        "kind": "decide",
        "payload": {"n": 1},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_1"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_1", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_2(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_2",
        "kind": "decide",
        "payload": {"n": 2},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_2"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_2", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_3(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_3",
        "kind": "decide",
        "payload": {"n": 3},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_3"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_3", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_4(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_4",
        "kind": "decide",
        "payload": {"n": 4},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_4"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_4", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_5(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_5",
        "kind": "decide",
        "payload": {"n": 5},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_5"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_5", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_6(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_6",
        "kind": "decide",
        "payload": {"n": 6},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_6"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_6", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_7(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_7",
        "kind": "decide",
        "payload": {"n": 7},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_7"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_7", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_8(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_8",
        "kind": "decide",
        "payload": {"n": 8},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_8"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_8", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_9(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_9",
        "kind": "decide",
        "payload": {"n": 9},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_9"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_9", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_10(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_10",
        "kind": "decide",
        "payload": {"n": 10},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_10"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_10", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_11(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_11",
        "kind": "decide",
        "payload": {"n": 11},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_11"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_11", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_12(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_12",
        "kind": "decide",
        "payload": {"n": 12},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_12"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_12", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_13(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_13",
        "kind": "decide",
        "payload": {"n": 13},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_13"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_13", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_14(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_14",
        "kind": "decide",
        "payload": {"n": 14},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_14"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_14", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_15(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_15",
        "kind": "decide",
        "payload": {"n": 15},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_15"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_15", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_16(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_16",
        "kind": "decide",
        "payload": {"n": 16},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_16"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_16", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_17(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_17",
        "kind": "decide",
        "payload": {"n": 17},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_17"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_17", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_18(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_18",
        "kind": "decide",
        "payload": {"n": 18},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_18"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_18", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_19(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_19",
        "kind": "decide",
        "payload": {"n": 19},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_19"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_19", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_20(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_20",
        "kind": "decide",
        "payload": {"n": 20},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_20"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_20", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_21(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_21",
        "kind": "decide",
        "payload": {"n": 21},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_21"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_21", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_22(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_22",
        "kind": "decide",
        "payload": {"n": 22},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_22"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_22", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_23(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_23",
        "kind": "decide",
        "payload": {"n": 23},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_23"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_23", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_24(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_24",
        "kind": "decide",
        "payload": {"n": 24},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_24"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_24", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_25(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_25",
        "kind": "decide",
        "payload": {"n": 25},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_25"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_25", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_26(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_26",
        "kind": "decide",
        "payload": {"n": 26},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_26"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_26", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_27(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_27",
        "kind": "decide",
        "payload": {"n": 27},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_27"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_27", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_28(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_28",
        "kind": "decide",
        "payload": {"n": 28},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_28"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_28", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_29(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_29",
        "kind": "decide",
        "payload": {"n": 29},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_29"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_29", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_30(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_30",
        "kind": "decide",
        "payload": {"n": 30},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_30"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_30", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_31(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_31",
        "kind": "decide",
        "payload": {"n": 31},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_31"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_31", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_32(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_32",
        "kind": "decide",
        "payload": {"n": 32},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_32"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_32", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_33(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_33",
        "kind": "decide",
        "payload": {"n": 33},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_33"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_33", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_34(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_34",
        "kind": "decide",
        "payload": {"n": 34},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_34"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_34", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_35(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_35",
        "kind": "decide",
        "payload": {"n": 35},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_35"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_35", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_36(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_36",
        "kind": "decide",
        "payload": {"n": 36},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_36"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_36", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_37(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_37",
        "kind": "decide",
        "payload": {"n": 37},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_37"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_37", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_38(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_38",
        "kind": "decide",
        "payload": {"n": 38},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_38"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_38", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_append_verify_tail_status_39(client):
    r = client.post("/omnifabric/append", json={
        "ledger": "court_39",
        "kind": "decide",
        "payload": {"n": 39},
        "quorum": ["a", "b"],
    })
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["seq"] >= 1
    assert ev["ledger"] == "court_39"
    v = client.get("/omnifabric/verify-chain")
    assert v.status_code == 200
    assert v.json()["ok"] is True
    t = client.get("/omnifabric/tail", params={"ledger": "court_39", "limit": 5})
    assert t.status_code == 200
    assert len(t.json()["events"]) >= 1
    s = client.get("/omnifabric/status")
    assert s.status_code == 200
    assert "fabric" in s.json()

def test_query_ledger_register_checkpoint_0(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_0", "description": "d0"})
    client.post("/omnifabric/append", json={"ledger": "reg_0", "kind": "k", "payload": {"i": 0}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_0", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_0" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_1(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_1", "description": "d1"})
    client.post("/omnifabric/append", json={"ledger": "reg_1", "kind": "k", "payload": {"i": 1}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_1", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_1" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_2(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_2", "description": "d2"})
    client.post("/omnifabric/append", json={"ledger": "reg_2", "kind": "k", "payload": {"i": 2}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_2", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_2" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_3(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_3", "description": "d3"})
    client.post("/omnifabric/append", json={"ledger": "reg_3", "kind": "k", "payload": {"i": 3}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_3", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_3" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_4(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_4", "description": "d4"})
    client.post("/omnifabric/append", json={"ledger": "reg_4", "kind": "k", "payload": {"i": 4}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_4", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_4" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_5(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_5", "description": "d5"})
    client.post("/omnifabric/append", json={"ledger": "reg_5", "kind": "k", "payload": {"i": 5}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_5", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_5" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_6(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_6", "description": "d6"})
    client.post("/omnifabric/append", json={"ledger": "reg_6", "kind": "k", "payload": {"i": 6}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_6", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_6" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_7(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_7", "description": "d7"})
    client.post("/omnifabric/append", json={"ledger": "reg_7", "kind": "k", "payload": {"i": 7}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_7", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_7" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_8(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_8", "description": "d8"})
    client.post("/omnifabric/append", json={"ledger": "reg_8", "kind": "k", "payload": {"i": 8}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_8", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_8" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_9(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_9", "description": "d9"})
    client.post("/omnifabric/append", json={"ledger": "reg_9", "kind": "k", "payload": {"i": 9}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_9", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_9" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_10(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_10", "description": "d10"})
    client.post("/omnifabric/append", json={"ledger": "reg_10", "kind": "k", "payload": {"i": 10}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_10", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_10" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_11(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_11", "description": "d11"})
    client.post("/omnifabric/append", json={"ledger": "reg_11", "kind": "k", "payload": {"i": 11}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_11", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_11" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_12(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_12", "description": "d12"})
    client.post("/omnifabric/append", json={"ledger": "reg_12", "kind": "k", "payload": {"i": 12}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_12", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_12" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_13(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_13", "description": "d13"})
    client.post("/omnifabric/append", json={"ledger": "reg_13", "kind": "k", "payload": {"i": 13}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_13", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_13" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_14(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_14", "description": "d14"})
    client.post("/omnifabric/append", json={"ledger": "reg_14", "kind": "k", "payload": {"i": 14}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_14", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_14" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_15(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_15", "description": "d15"})
    client.post("/omnifabric/append", json={"ledger": "reg_15", "kind": "k", "payload": {"i": 15}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_15", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_15" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_16(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_16", "description": "d16"})
    client.post("/omnifabric/append", json={"ledger": "reg_16", "kind": "k", "payload": {"i": 16}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_16", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_16" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_17(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_17", "description": "d17"})
    client.post("/omnifabric/append", json={"ledger": "reg_17", "kind": "k", "payload": {"i": 17}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_17", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_17" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_18(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_18", "description": "d18"})
    client.post("/omnifabric/append", json={"ledger": "reg_18", "kind": "k", "payload": {"i": 18}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_18", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_18" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_query_ledger_register_checkpoint_19(client):
    client.post("/omnifabric/ledgers/register", json={"name": "reg_19", "description": "d19"})
    client.post("/omnifabric/append", json={"ledger": "reg_19", "kind": "k", "payload": {"i": 19}, "quorum": []})
    q = client.post("/omnifabric/query", json={"ledger": "reg_19", "limit": 10})
    assert q.status_code == 200
    assert len(q.json()["events"]) >= 1
    c = client.post("/omnifabric/checkpoint")
    assert c.status_code == 200
    ledgers = client.get("/omnifabric/ledgers")
    assert any(x["name"] == "reg_19" for x in ledgers.json()["ledgers"])
    rec = client.post("/omnifabric/reconcile")
    assert rec.status_code == 200

def test_append_requires_ledger_kind(client):
    r = client.post("/omnifabric/append", json={"ledger": "", "kind": ""})
    assert r.status_code == 400


def test_verify_full_evidence(client):
    client.post("/omnifabric/append", json={"ledger": "E", "kind": "k", "payload": {}, "quorum": []})
    r = client.get("/omnifabric/verify-chain", params={"full": True})
    assert r.status_code == 200
    body = r.json()
    assert "report" in body and body["report"]["ok"] is True
