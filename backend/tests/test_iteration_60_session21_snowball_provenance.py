"""
Iteration 60 — Session 21: Snowball quick-wins + Provenance/Invalidation.

Validates:
  • POST /api/snowball/{pid}/lock-all → locks every built-but-unlocked stage; reflected in GET.
  • GET /api/snowball/{pid}/gdd.md → text/markdown, body starts with '# 🎮 Game Design Document',
    Content-Disposition attachment filename ends '_GDD.md'.
  • Provenance + dependency-invalidation graph:
      - Forge the `assets` stage (deterministic) → poll job done
      - GET /api/snowball/{pid}: provenance['asset_manifest'].agent == 'AssetPipelineAgent';
        stale map contains 'build_manifest'; the build step has stale=true; stale_count>=1.
      - GET /api/pipeline/{pid}/kb: top-level 'stale' and 'provenance' present; each artifact entry
        has a 'stale' boolean.
"""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
PID = "d02790d6d8174ff59bf7005221cd7609"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Snowball lock-all ────────────────────────────────────────────────────────
class TestSnowballLockAll:
    def test_lock_all_returns_ok_and_count(self, s):
        r = s.post(f"{BASE_URL}/api/snowball/{PID}/lock-all", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert "locked" in j and isinstance(j["locked"], list)
        assert "count" in j and j["count"] == len(j["locked"])

    def test_after_lock_all_built_steps_are_locked(self, s):
        # Idempotent re-lock to capture any newly-built stages
        s.post(f"{BASE_URL}/api/snowball/{PID}/lock-all", timeout=15)
        r = s.get(f"{BASE_URL}/api/snowball/{PID}", timeout=15)
        assert r.status_code == 200
        snow = r.json()
        # every step that is BUILT (done) and is a real stage should be locked
        built_stages = [st for st in snow["steps"] if st["key"] != "mode" and st.get("done")]
        assert built_stages, "expected at least one built stage on the rich game"
        unlocked = [st for st in built_stages if not st.get("locked")]
        assert unlocked == [], f"built stages still unlocked after lock-all: {[u['key'] for u in unlocked]}"
        # locked count > 0
        assert snow.get("locked", 0) >= len(built_stages)


# ── GDD markdown export ─────────────────────────────────────────────────────
class TestGddExport:
    def test_gdd_md_endpoint(self, s):
        r = s.get(f"{BASE_URL}/api/snowball/{PID}/gdd.md", timeout=15)
        assert r.status_code == 200, r.text
        ctype = r.headers.get("Content-Type", "")
        assert "text/markdown" in ctype, f"unexpected content-type: {ctype}"
        body = r.text
        assert body.startswith("# 🎮 Game Design Document"), body[:120]
        dispo = r.headers.get("Content-Disposition", "")
        assert "attachment" in dispo.lower()
        # filename portion must end with _GDD.md
        stripped = dispo.rstrip().rstrip('"')
        assert stripped.endswith("_GDD.md"), dispo


# ── Provenance + dependency invalidation ─────────────────────────────────────
class TestProvenanceAndInvalidation:
    def test_asset_forge_then_invalidation(self, s):
        # Kick off the deterministic assets forge
        r = s.post(f"{BASE_URL}/api/pipeline/{PID}/forge/assets/async", timeout=20)
        assert r.status_code == 200, r.text
        job = r.json()
        jid = job.get("job_id")
        assert jid, job

        # Poll for job done (deterministic, should be quick)
        done = False
        for _ in range(30):
            time.sleep(2)
            jr = s.get(f"{BASE_URL}/api/playable/job/{jid}", timeout=15).json()
            st = jr.get("job_status")
            if st in ("done", "error"):
                assert st == "done", jr
                done = True
                break
        assert done, "assets forge job did not finish in time"

        # Verify provenance + stale + step flag in snowball
        snow = s.get(f"{BASE_URL}/api/snowball/{PID}", timeout=15).json()
        prov = snow.get("provenance") or {}
        am_prov = prov.get("asset_manifest") or {}
        assert am_prov.get("agent") == "AssetPipelineAgent", am_prov

        stale = snow.get("stale") or {}
        assert "build_manifest" in stale, f"build_manifest not stale after assets forge; stale={stale}"
        assert snow.get("stale_count", 0) >= 1

        build_step = next((st for st in snow["steps"] if st["key"] == "build"), None)
        assert build_step is not None
        assert build_step.get("stale") is True, build_step

    def test_kb_exposes_stale_and_provenance(self, s):
        kb = s.get(f"{BASE_URL}/api/pipeline/{PID}/kb", timeout=15).json()
        assert "stale" in kb and isinstance(kb["stale"], dict)
        assert "provenance" in kb and isinstance(kb["provenance"], dict)
        arts = kb.get("artifacts") or []
        assert arts, kb
        for a in arts:
            assert "stale" in a and isinstance(a["stale"], bool), a
        # asset_manifest provenance recorded
        assert kb["provenance"].get("asset_manifest", {}).get("agent") == "AssetPipelineAgent"
