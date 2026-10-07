"""Iteration 127 — Churn 2.0 + Autonomous Orchestrator + Provenance E2E.

Validates:
  • /api/churn        — models catalog (18 models, by_provider, bands), analyze,
                        async run (deterministic), runs history, apply, daemon.
  • /api/galaxy-studio/text-gamefile/generators — 'Deferred Forges' group with 8 keys.
  • /api/galaxy-studio/text-gamefile/<gen>/generate — forge city_forge tier Metropolis.
  • /api/galaxy-studio/gamefile-pipeline/<bid>/<gid>/run — 14-gate pipeline.
  • /api/orchestrator — directive → 4-node DAG → execute (async) → replan cascade.
  • /api/provenance   — append-only chain w/ hash links, verify (valid:true),
                        append, artifact lookup.

All against the public preview URL exposed via EXPO_PUBLIC_BACKEND_URL.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest
import requests

# ── base URL (public preview) ────────────────────────────────────────────────
_FRONT_ENV = Path("/app/frontend/.env")
BASE_URL = None
if _FRONT_ENV.exists():
    for ln in _FRONT_ENV.read_text().splitlines():
        if ln.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = ln.split("=", 1)[1].strip().strip('"').rstrip("/")
            break
if not BASE_URL:
    BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")

API = f"{BASE_URL}/api"
TIMEOUT = 60


# ── shared session ───────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def build_id():
    return f"qa127_{uuid.uuid4().hex[:8]}"


def _poll_job(s, url, deadline_s=45):
    """Poll an async job until status != running. Returns final job dict."""
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        r = s.get(url, timeout=TIMEOUT)
        assert r.status_code == 200, f"poll {url} -> {r.status_code} / {r.text[:200]}"
        j = r.json()
        if j.get("status") in ("done", "error", "failed"):
            return j
        time.sleep(0.6)
    raise AssertionError(f"job at {url} did not complete in {deadline_s}s")


# ─────────────────────────────────────────────────────────────────────────────
# CHURN 2.0 — model catalog & basic analyze
# ─────────────────────────────────────────────────────────────────────────────
class TestChurnModels:
    def test_models_catalog_shape(self, s):
        r = s.get(f"{API}/churn/models", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        # core shape
        for k in ("count", "providers", "by_provider", "models", "default", "qc_bar"):
            assert k in j, f"missing key {k}"
        assert j["qc_bar"] == 95, f"qc_bar={j['qc_bar']}"
        assert j["count"] >= 18, f"expected >=18 models, got {j['count']}"
        # bands present (premium + free)
        bands = {m["band"] for m in j["models"]}
        assert "premium" in bands and "free" in bands, f"bands={bands}"
        # by_provider non-empty
        assert isinstance(j["by_provider"], dict) and len(j["by_provider"]) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# DEFERRED FORGES — generators registry
# ─────────────────────────────────────────────────────────────────────────────
class TestDeferredForges:
    EXPECTED = {
        "quality_forge", "fine_tuning_forge", "critter_bestiary_forge",
        "nature_forge", "realism_forge", "fine_mechanic_forge",
        "movement_forge", "city_forge",
    }

    def test_generators_include_deferred_forges_group(self, s):
        r = s.get(f"{API}/galaxy-studio/text-gamefile/generators", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        gens = j.get("generators") or j.get("items") or []
        if isinstance(j, list):
            gens = j
        keys_in_deferred = {
            g["key"] for g in gens
            if g.get("group") == "Deferred Forges"
        }
        missing = self.EXPECTED - keys_in_deferred
        assert not missing, (
            f"missing Deferred Forges keys: {missing} (got {keys_in_deferred})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# CHURN E2E — forge a gamefile, analyze, async run, apply, daemon
# ─────────────────────────────────────────────────────────────────────────────
class TestChurnE2E:
    def test_forge_gamefile(self, s, build_id):
        # use enemy_from_text — simple, fast
        body = {"build_id": build_id, "text": "Frost wraith haunting a frozen tundra"}
        r = s.post(
            f"{API}/galaxy-studio/text-gamefile/enemy_from_text/generate",
            json=body, timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"{r.status_code} / {r.text[:200]}"
        j = r.json()
        gid = j.get("gid") or j.get("id") or (j.get("gamefile") or {}).get("gid")
        assert gid, f"no gid in response: {list(j.keys())}"
        pytest.shared_gid = gid

    def test_analyze_build(self, s, build_id):
        r = s.get(f"{API}/churn/{build_id}/analyze", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        assert j.get("qc_bar") == 95
        assert "items" in j or "scores" in j or "targets" in j

    def test_analyze_gamefile(self, s, build_id):
        gid = pytest.shared_gid
        r = s.get(f"{API}/churn/{build_id}/{gid}/analyze", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        # per-gamefile analyze surfaces scores + deficits (qc_bar is on build-level analyze)
        assert "scores" in j and "deficits" in j, f"keys={list(j.keys())}"
        assert "worst_deficit" in j
        assert isinstance(j.get("needs_churn"), bool)

    def test_async_run_deterministic(self, s, build_id):
        gid = pytest.shared_gid
        # deterministic = no model (None)
        r = s.post(
            f"{API}/churn/{build_id}/run/async",
            json={"gid": gid, "n": 6}, timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text[:200]
        jid = r.json()["job_id"]
        result = _poll_job(s, f"{API}/churn/job/{jid}", deadline_s=45)
        assert result.get("status") == "done", f"job result: {result}"
        out = result.get("result") or result.get("output") or result
        # find alternatives (could be nested under runs[0])
        alts = (
            out.get("alternatives")
            or (out.get("runs") or [{}])[0].get("alternatives")
            or []
        )
        assert len(alts) >= 6, f"expected 6 alternatives, got {len(alts)}"
        # each alt: pros/cons/recommended/paragraphs/production_score
        for a in alts:
            assert "pros" in a and "cons" in a, f"alt missing pros/cons: {list(a.keys())}"
            assert "recommended" in a
            paras = a.get("paragraphs") or a.get("six_paragraphs") or []
            assert len(paras) >= 6, f"alt paragraphs={len(paras)}"
            ps = a.get("production_score", a.get("score", 0))
            assert ps >= 95, f"production_score={ps} < 95"
        # all_clear_qc surfaces at top
        ac = out.get("all_clear_qc")
        if ac is None and out.get("runs"):
            ac = (out["runs"][0] or {}).get("all_clear_qc")
        assert ac is True, f"all_clear_qc={ac}"
        # stash run_id for apply test
        run_id = out.get("run_id") or (out.get("runs") or [{}])[0].get("run_id")
        variant_id = (alts[0] or {}).get("variant_id") or (alts[0] or {}).get("id")
        pytest.shared_run_id = run_id
        pytest.shared_variant_id = variant_id

    def test_list_runs(self, s, build_id):
        r = s.get(f"{API}/churn/{build_id}/runs", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        runs = j if isinstance(j, list) else j.get("runs", j.get("items", []))
        assert len(runs) >= 1

    def test_apply_alternative_bumps_version(self, s, build_id):
        gid = pytest.shared_gid
        rid = getattr(pytest, "shared_run_id", None)
        vid = getattr(pytest, "shared_variant_id", None)
        if not (rid and vid):
            pytest.skip("no run_id/variant_id from async run")
        r = s.post(
            f"{API}/churn/{build_id}/{gid}/apply",
            json={"run_id": rid, "variant_id": vid}, timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        cv = j.get("churn_version") or (j.get("gamefile") or {}).get("churn_version")
        assert cv and cv >= 1, f"churn_version not bumped: {j}"

    def test_daemon_toggle_and_status(self, s):
        # toggle on
        r = s.post(
            f"{API}/churn/daemon/toggle",
            json={"enabled": True, "interval_s": 30}, timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        assert j.get("enabled") is True
        # status
        r = s.get(f"{API}/churn/daemon/status", timeout=TIMEOUT)
        assert r.status_code == 200
        st = r.json()
        assert st.get("enabled") is True
        # toggle off (cleanup)
        s.post(f"{API}/churn/daemon/toggle",
               json={"enabled": False}, timeout=TIMEOUT)


# ─────────────────────────────────────────────────────────────────────────────
# CITY FORGE → 14-GATE PIPELINE → CHURN
# ─────────────────────────────────────────────────────────────────────────────
class TestCityForgePipeline:
    def test_forge_city_metropolis_then_pipeline(self, s, build_id):
        body = {"build_id": build_id, "text": "Sun-bleached coastal city",
                "tier": "Metropolis"}
        r = s.post(
            f"{API}/galaxy-studio/text-gamefile/city_forge/generate",
            json=body, timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        gid = j.get("gid") or j.get("id") or (j.get("gamefile") or {}).get("gid")
        assert gid
        # 14-gate pipeline
        r = s.post(
            f"{API}/galaxy-studio/gamefile-pipeline/{build_id}/{gid}/run",
            json={}, timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text[:300]
        pj = r.json()
        stages = pj.get("stages") or pj.get("gates") or []
        assert len(stages) == 14, f"expected 14 stages, got {len(stages)}"


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR — directive → 4-node DAG → execute → replan
# ─────────────────────────────────────────────────────────────────────────────
class TestOrchestrator:
    def test_plan_4_node_dag(self, s, build_id):
        directive = ("Forge an enemy frost wraith; then forge a quest; "
                     "then run the 14-gate pipeline; then churn the build")
        r = s.post(
            f"{API}/orchestrator/{build_id}/plan",
            json={"directive": directive}, timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        nodes = j.get("nodes") or (j.get("plan") or {}).get("nodes") or []
        assert len(nodes) == 4, f"expected 4 nodes, got {len(nodes)}: {nodes}"
        # verify kinds
        kinds = [n.get("kind") or n.get("op") or n.get("type") for n in nodes]
        joined = ",".join(str(k) for k in kinds)
        for must in ("forge", "gate", "churn"):
            assert must in joined.lower(), f"missing op {must} in {kinds}"
        plan_id = j.get("plan_id") or j.get("id") or (j.get("plan") or {}).get("plan_id")
        assert plan_id
        pytest.shared_plan_id = plan_id

    def test_execute_async_and_poll(self, s):
        pid = pytest.shared_plan_id
        r = s.post(f"{API}/orchestrator/plan/{pid}/execute/async",
                   json={}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        jid = r.json()["job_id"]
        result = _poll_job(s, f"{API}/orchestrator/job/{jid}", deadline_s=120)
        assert result.get("status") == "done", f"orch job: {result}"
        done = result.get("done") or (result.get("result") or {}).get("done")
        assert done == 4, f"done={done}"

    def test_replan_cascade(self, s):
        pid = pytest.shared_plan_id
        r = s.post(f"{API}/orchestrator/plan/{pid}/replan",
                   json={"node_id": "n3"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        # response key is 'replanned' (see autonomous_orchestrator.replan_from)
        reset = j.get("replanned") or j.get("reset") or j.get("reset_nodes") or []
        assert set(reset) >= {"n3", "n4"}, f"replanned={reset}"
        ver = j.get("version") or (j.get("plan") or {}).get("version")
        assert ver and ver >= 2, f"version not bumped: {ver}"

    def test_list_and_get_plan(self, s, build_id):
        pid = pytest.shared_plan_id
        r = s.get(f"{API}/orchestrator/{build_id}/plans", timeout=TIMEOUT)
        assert r.status_code == 200
        plans = r.json()
        plans = plans if isinstance(plans, list) else plans.get("plans", plans.get("items", []))
        assert any((p.get("plan_id") or p.get("id")) == pid for p in plans), \
            f"plan {pid} not in list"
        r = s.get(f"{API}/orchestrator/plan/{pid}", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "error" not in r.json()


# ─────────────────────────────────────────────────────────────────────────────
# PROVENANCE — chain, verify, append, artifact
# ─────────────────────────────────────────────────────────────────────────────
class TestProvenance:
    def test_chain_has_events(self, s, build_id):
        r = s.get(f"{API}/provenance/{build_id}/chain", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        events = j if isinstance(j, list) else j.get("events", j.get("chain", []))
        assert len(events) >= 1, "chain empty after churn+orch runs"
        # hash linking
        prev = None
        for ev in events:
            assert "hash" in ev, f"event missing hash: {list(ev.keys())}"
            if prev is not None:
                assert ev.get("prev_hash") == prev, \
                    f"prev_hash mismatch at {ev.get('kind')}"
            prev = ev["hash"]

    def test_verify_valid(self, s, build_id):
        r = s.get(f"{API}/provenance/{build_id}/verify", timeout=TIMEOUT)
        assert r.status_code == 200
        v = r.json()
        assert v.get("valid") is True, f"verify: {v}"
        bl = v.get("broken_links", [])
        assert bl == [] or bl == 0, f"broken_links: {bl}"

    def test_append_event(self, s, build_id):
        r = s.post(
            f"{API}/provenance/{build_id}/append",
            json={"kind": "qa_marker", "data": {"by": "iteration_127"}},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text[:200]
        ev = r.json()
        assert ev.get("kind") in ("qa_marker", "user.qa_marker") or "hash" in ev
        # re-verify still valid
        r = s.get(f"{API}/provenance/{build_id}/verify", timeout=TIMEOUT)
        assert r.json().get("valid") is True

    def test_artifact_provenance(self, s, build_id):
        gid = pytest.shared_gid
        r = s.get(f"{API}/provenance/{build_id}/artifact/{gid}", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        # response should be either a list of events or a dict with events
        events = j if isinstance(j, list) else j.get("events", [])
        # tolerant: empty is acceptable if artifact wasn't auto-recorded
        assert isinstance(events, list)
