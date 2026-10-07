"""
test_gamefile_pipeline.py — SOTA Gamefile Pipeline regression suite.

Covers:
 • GET /api/galaxy-studio/gamefile-pipeline/gates (8 gates, order, params, controller, traffic)
 • POST /api/galaxy-studio/gamefile-pipeline/{build_id}/{gid}/run (volume math, mint count, 8 stages, all_passed)
 • GET /api/galaxy-studio/gamefile-pipeline/controller/status (controller, traffic, params, systems)
 • GET /api/galaxy-studio/gates/stages (sota_params.aaa_threshold=97 + gate_controller + traffic_controller)
 • Sibling minting effect: list grows by at least minted_count after pipeline run.
"""
from __future__ import annotations

import os
import time
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set in frontend/.env"

EXPECTED_ORDER = [
    "page_scale", "audit_incoming", "extender", "extrapolator",
    "enhancer", "quality_control", "fidelity_control", "audit_outward",
]


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def build_id():
    return f"qa_pipe_{uuid.uuid4().hex[:6]}"


# ─────────────────────────── gates listing ─────────────────────────────
def test_pipeline_gates_listing(http):
    r = http.get(f"{BASE_URL}/api/galaxy-studio/gamefile-pipeline/gates", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("gate_count") == 8
    gates = body.get("gates") or []
    assert len(gates) == 8
    assert [g["key"] for g in gates] == EXPECTED_ORDER, f"unexpected order: {[g['key'] for g in gates]}"
    params = body.get("params") or {}
    assert params.get("pages_per_choice") == 200
    assert "controller" in body and isinstance(body["controller"].get("runs"), int)
    traffic = body.get("traffic") or {}
    for k in ("concurrency_cap", "in_flight", "dispatched_total"):
        assert k in traffic, f"missing traffic.{k}"


# ─────────────────────────── controller status ─────────────────────────
def test_controller_status(http):
    r = http.get(f"{BASE_URL}/api/galaxy-studio/gamefile-pipeline/controller/status", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    ctrl = body.get("controller") or {}
    assert ctrl.get("gates") == 8
    assert isinstance(ctrl.get("runs"), int)
    traffic = body.get("traffic") or {}
    for k in ("concurrency_cap", "in_flight", "dispatched_total"):
        assert k in traffic
    params = body.get("params") or {}
    assert params.get("pages_per_choice") == 200
    systems = body.get("systems") or []
    assert len(systems) == 8
    sys_keys = [s["gate"] for s in systems]
    assert sys_keys == EXPECTED_ORDER


# ─────────────────────── gates/stages SOTA params ─────────────────────
def test_gates_stages_sota_params(http):
    r = http.get(f"{BASE_URL}/api/galaxy-studio/gates/stages", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    sp = body.get("sota_params") or {}
    assert sp.get("aaa_threshold") == 97, f"aaa_threshold expected 97, got {sp.get('aaa_threshold')}"
    assert isinstance(sp.get("gate_controller"), dict) and sp["gate_controller"], "gate_controller missing/empty"
    assert isinstance(sp.get("traffic_controller"), dict) and sp["traffic_controller"], "traffic_controller missing/empty"


# ─────────────────────── full run: quest_from_text ─────────────────────
def _forge(http, build_id, key, brief):
    r = http.post(
        f"{BASE_URL}/api/galaxy-studio/text-gamefile/{key}/generate",
        json={"text": brief, "enrich": False, "build_id": build_id}, timeout=30,
    )
    assert r.status_code == 200, f"forge {key}: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body.get("id"), f"forge {key}: no id in response {body}"
    return body


def _list(http, build_id):
    r = http.get(f"{BASE_URL}/api/galaxy-studio/text-gamefile/{build_id}/list", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body.get("items") or body.get("gamefiles") or body.get("results") or []
    if not items and isinstance(body, list):
        items = body
    return items


def test_full_pipeline_quest_from_text(http, build_id):
    quest = _forge(http, build_id,
                   "quest_from_text",
                   "A wandering ranger named Kael must retrieve the sun-stone from the ruined temple.")
    gid = quest["id"]
    pre_list = _list(http, build_id)
    pre_count = len(pre_list)

    r = http.post(
        f"{BASE_URL}/api/galaxy-studio/gamefile-pipeline/{build_id}/{gid}/run",
        json={"persist": True}, timeout=45,
    )
    assert r.status_code == 200, f"run: {r.status_code} {r.text[:400]}"
    body = r.json()
    assert body.get("gate_count") == 8
    stages = body.get("stages") or []
    assert len(stages) == 8
    assert [s["key"] for s in stages] == EXPECTED_ORDER
    for s in stages:
        assert "report" in s and isinstance(s["report"], dict), f"stage {s.get('key')} missing report"
        assert "passed" in s, f"stage {s.get('key')} missing passed"
    assert body.get("all_passed") is True, f"not all passed: {[(s['key'], s['passed']) for s in stages]}"

    volume = body.get("volume") or {}
    assert volume.get("pages_per_choice") == 200
    choices = volume.get("choices")
    assert isinstance(choices, int) and choices >= 1
    total_pages = volume.get("total_pages")
    assert total_pages == choices * 200, f"pages math: {total_pages} != {choices}*200"
    assert body.get("pages") == total_pages
    assert isinstance(volume.get("est_words"), int) and volume["est_words"] == total_pages * 450

    minted_count = body.get("minted_count") or 0
    assert minted_count >= 1, f"expected ≥1 minted companion, got {minted_count}"

    traffic = body.get("traffic") or {}
    assert "concurrency_cap" in traffic and "dispatched_total" in traffic

    # sibling minting → list grows
    time.sleep(0.5)
    post_list = _list(http, build_id)
    assert len(post_list) >= pre_count + minted_count, (
        f"list did not grow as expected: pre={pre_count}, post={len(post_list)}, minted={minted_count}"
    )


def test_full_pipeline_enemy_from_text(http, build_id):
    enemy = _forge(http, build_id,
                   "enemy_from_text",
                   "A horrid bog-wight that drags victims into the marsh, immune to fire but weak to silver.")
    gid = enemy["id"]
    r = http.post(
        f"{BASE_URL}/api/galaxy-studio/gamefile-pipeline/{build_id}/{gid}/run",
        json={"persist": True}, timeout=45,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("all_passed") is True
    volume = body.get("volume") or {}
    assert volume.get("pages_per_choice") == 200
    assert volume.get("total_pages") == volume.get("choices") * 200
    assert body.get("minted_count", 0) >= 1


def test_run_missing_gamefile(http, build_id):
    r = http.post(
        f"{BASE_URL}/api/galaxy-studio/gamefile-pipeline/{build_id}/does_not_exist_xyz/run",
        json={"persist": False}, timeout=15,
    )
    # endpoint returns 200 with error key per implementation
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("error") == "gamefile_not_found"
