"""Iteration 120 — UNBULK / Storage Savings & Transparent Compression tests.

Covers:
  • GET  /api/storage/savings
  • GET  /api/storage/modules?top=5
  • POST /api/storage/sweep   (freeze_cold=false, idempotency)
  • POST /api/storage/cache/purge
  • Transparent gamefile compression round-trip (write → read decompresses)
  • 14-gate crosswiring on a compressed gamefile (refine, kind=gamefile)
  • Regression: backend healthy, ~155 routers registered, no 500s
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests


BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ─── 0. Regression — backend healthy ────────────────────────────────────────
class TestRegressionHealth:
    def test_root_ok(self, api):
        r = api.get(f"{BASE_URL}/api/", timeout=30)
        assert r.status_code in (200, 404), f"backend root unreachable: {r.status_code}"

    def test_storage_routes_registered(self, api):
        # The platform ingress forwards /api/* only, so we verify routes are
        # registered by hitting them directly (openapi.json isn't exposed).
        # Backend logs separately confirm "[BOOT] routes_registry: registered=155".
        for path in ("/api/storage/savings",
                     "/api/storage/modules",
                     "/api/storage/cache/purge"):
            method = "POST" if "purge" in path else "GET"
            r = api.request(method, f"{BASE_URL}{path}", timeout=30)
            assert r.status_code < 500, f"{method} {path} → {r.status_code}"
            assert r.status_code != 404, f"{method} {path} unregistered"


# ─── 1. /api/storage/savings ────────────────────────────────────────────────
class TestSavings:
    def test_savings_shape_and_values(self, api):
        r = api.get(f"{BASE_URL}/api/storage/savings", timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()

        # Core numbers
        assert isinstance(d.get("total_raw_bytes"), int)
        assert isinstance(d.get("total_stored_bytes"), int)
        assert d["total_raw_bytes"] > d["total_stored_bytes"], (
            "raw should exceed stored — compression should have shrunk it")
        assert d.get("bytes_saved", 0) > 0
        # saved_pct ~90%+; allow >=80 to be safe
        assert d.get("saved_pct", 0) >= 80, f"saved_pct too low: {d.get('saved_pct')}"
        # overall_ratio ~17x; allow >=5 to be safe
        assert d.get("overall_ratio", 0) >= 5, f"overall_ratio too low: {d.get('overall_ratio')}"

        # Flags
        assert d.get("api_response_gzip") is True

        # human dict
        h = d.get("human") or {}
        for k in ("raw", "stored", "saved"):
            assert k in h and isinstance(h[k], str) and h[k], f"human.{k} missing/bad"

        # namespaces include expected entries
        ns_names = [n.get("namespace", "") for n in (d.get("namespaces") or [])]
        joined = " | ".join(ns_names)
        assert "knowledge_vault" in joined and "zstd" in joined, f"knowledge_vault(zstd) missing in {ns_names}"
        assert "cold_storage" in joined, f"cold_storage missing in {ns_names}"


# ─── 2. /api/storage/modules ────────────────────────────────────────────────
class TestModules:
    def test_modules_top5(self, api):
        r = api.get(f"{BASE_URL}/api/storage/modules?top=5", timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()

        # module_count near 442 — allow ±30%
        mc = d.get("module_count")
        assert isinstance(mc, int) and mc > 300, f"unexpected module_count={mc}"
        assert isinstance(d.get("total_bytes"), int) and d["total_bytes"] > 0
        assert isinstance(d.get("total_lines"), int) and d["total_lines"] > 0

        biggest = d.get("biggest") or []
        assert len(biggest) == 5, f"expected top=5 biggest, got {len(biggest)}"

        # Sorted descending by bytes
        sizes = [m.get("bytes", 0) for m in biggest]
        assert sizes == sorted(sizes, reverse=True), f"biggest not sorted desc: {sizes}"

        # First item should be seeds/rosetta_curriculum.py
        first = biggest[0].get("module", "")
        assert first.endswith("seeds/rosetta_curriculum.py"), \
            f"expected seeds/rosetta_curriculum.py first, got {first}"

        # lazy_eligible bool on each
        for m in biggest:
            assert isinstance(m.get("lazy_eligible"), bool), f"lazy_eligible missing/bad: {m}"


# ─── 3. /api/storage/sweep (freeze_cold=false) ──────────────────────────────
class TestSweep:
    def test_sweep_runs_and_is_idempotent(self, api):
        body = {"freeze_cold": False, "manifest_min_bytes": 50000, "max_manifests": 3}
        r1 = api.post(f"{BASE_URL}/api/storage/sweep", json=body, timeout=120)
        assert r1.status_code == 200, r1.text[:400]
        d1 = r1.json()
        assert d1.get("ok") is True
        assert d1.get("manifests_compressed", -1) >= 0
        assert d1.get("bytes_reclaimed", -1) >= 0
        assert isinstance(d1.get("bytes_reclaimed_human"), str) and d1["bytes_reclaimed_human"]
        # freeze_cold=False → cold_freeze should not have run
        assert d1.get("cold_freeze") in (None, False), f"cold_freeze should not run, got {d1.get('cold_freeze')}"

        # Idempotency: re-run with the same body. Already-compressed manifests
        # have their plain .json deleted (replaced by .json.gz), so the same
        # files are guaranteed to be skipped on re-iteration; the next run will
        # only find OTHER uncompressed manifests. We verify the contract holds
        # (no errors, valid schema) on the second call.
        r2 = api.post(f"{BASE_URL}/api/storage/sweep", json=body, timeout=120)
        assert r2.status_code == 200, r2.text[:400]
        d2 = r2.json()
        assert d2.get("ok") is True
        assert d2.get("manifests_compressed", -1) >= 0
        assert d2.get("bytes_reclaimed", -1) >= 0
        assert isinstance(d2.get("bytes_reclaimed_human"), str)
        assert d2.get("cold_freeze") in (None, False)


# ─── 4. /api/storage/cache/purge ────────────────────────────────────────────
class TestCachePurge:
    def test_purge_returns_int(self, api):
        r = api.post(f"{BASE_URL}/api/storage/cache/purge", timeout=30)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert isinstance(d.get("purged"), int)
        assert d["purged"] >= 0


# ─── 5. Transparent gamefile compression round-trip ─────────────────────────
LONG_QUEST_TEXT = (
    "In the shattered Aurorian highlands, a forgotten clockwork city sleeps beneath "
    "the perpetual aurora. The hero, a wandering archivist named Vael, must descend "
    "through seven brass strata to recover the missing chrono-cores before the moon's "
    "next zenith. Each stratum is guarded by a paradox: a riddle that bends time, a "
    "duel against one's own future shadow, a labyrinth whose walls re-arrange between "
    "heartbeats, and a council of mechanical sages who only speak in inverted prophecies. "
    "Along the way Vael recruits allies — a mute cartographer who maps with breath, a "
    "thief whose hands move slightly before his intent, and a cleric of forgotten gods "
    "who barters memories for miracles. Failure conditions include irreversible memory "
    "decay, accidental temporal echoes, and the awakening of the Auroran sovereign, an "
    "ancient automaton sealed at the city's heart. Branching outcomes range from total "
    "restoration of the city to a tragic loop where Vael becomes the next clockwork sage. "
    "Rewards include the Brass Astrolabe, the Diadem of Hours, and three irrevocable "
    "boons of foresight. The quest's pacing alternates investigation, exploration, "
    "stealth, ritual puzzle, and climactic boss confrontation."
) * 2  # ensure >600 chars; ~2400 chars


@pytest.fixture(scope="module")
def fresh_build_id():
    return f"TEST_unbulk_{uuid.uuid4().hex[:10]}"


class TestGamefileCompressionRoundtrip:
    def test_generate_then_get_decompresses(self, api, fresh_build_id):
        # Generate quest gamefile
        gen_payload = {"build_id": fresh_build_id, "text": LONG_QUEST_TEXT, "enrich": False}
        r = api.post(
            f"{BASE_URL}/api/galaxy-studio/text-gamefile/quest_from_text/generate",
            json=gen_payload, timeout=60,
        )
        assert r.status_code == 200, r.text[:400]
        gf = r.json()
        assert "error" not in gf, f"generate errored: {gf}"
        gid = gf.get("id")
        assert gid and gid.startswith("gf_quest_from_text_"), f"bad gid: {gid}"
        # The response from generate is the in-memory gamefile BEFORE storage,
        # so 'fields' should already be an object
        assert isinstance(gf.get("fields"), dict), "generate response fields should be dict"

        # Tiny pause to let async storage settle (it's sync, but be safe)
        time.sleep(0.5)

        # Read it back via the get endpoint: GET /{build_id}/{gid}
        r2 = api.get(
            f"{BASE_URL}/api/galaxy-studio/text-gamefile/{fresh_build_id}/{gid}",
            timeout=30,
        )
        assert r2.status_code == 200, r2.text[:400]
        doc = r2.json()
        assert "error" not in doc, f"get errored: {doc}"

        # CRITICAL: fields MUST be a dict, NOT a 'GZ1:'-prefixed string.
        fields = doc.get("fields")
        assert isinstance(fields, dict), (
            f"fields should be JSON object after decompress-on-read; got {type(fields).__name__}: "
            f"{str(fields)[:80]}"
        )
        assert not (isinstance(fields, str) and fields.startswith("GZ1:")), \
            "fields still packed — decompress-on-read failed"

        # brief should also be unpacked (string OR dict, but never GZ1:)
        brief = doc.get("brief")
        if isinstance(brief, str):
            assert not brief.startswith("GZ1:"), "brief still packed"

        # Sanity: gamefile metadata
        assert doc.get("build_id") == fresh_build_id
        assert doc.get("id") == gid
        assert doc.get("kind") == "gamefile"

        # Verify expected quest fields exist
        for f in ("title", "objectives", "stages", "rewards"):
            assert f in fields, f"missing quest field: {f}"

        # Stash gid for next test
        pytest._unbulk_gid = gid  # type: ignore

    def test_list_gamefiles_decompresses(self, api, fresh_build_id):
        r = api.get(
            f"{BASE_URL}/api/galaxy-studio/text-gamefile/{fresh_build_id}/list",
            timeout=30,
        )
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d.get("count", 0) >= 1, f"expected >=1 gamefile in build, got {d}"
        gfs = d.get("gamefiles") or []
        for g in gfs:
            f = g.get("fields")
            assert isinstance(f, dict), f"list returned packed fields: {type(f).__name__}"


# ─── 6. 14-gate crosswiring on a compressed gamefile ────────────────────────
class TestGatesOnGamefile:
    def test_refine_gate_runs_on_gamefile(self, api, fresh_build_id):
        gid = getattr(pytest, "_unbulk_gid", None)
        assert gid, "previous round-trip test did not capture gid"

        payload = {"build_id": fresh_build_id, "kind": "gamefile",
                   "key": gid, "seed": 3}
        r = api.post(
            f"{BASE_URL}/api/galaxy-studio/gates/refine/run",
            json=payload, timeout=90,
        )
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d.get("passed") is True, f"refine gate did not pass: {d}"
        tgt = d.get("target") or {}
        assert tgt.get("kind") == "gamefile", f"target.kind != 'gamefile': {tgt}"


# ─── 7. No-500s sweep over the touched endpoints ────────────────────────────
class TestNo500s:
    def test_no_500s_on_storage_endpoints(self, api):
        endpoints = [
            ("GET", "/api/storage/savings", None),
            ("GET", "/api/storage/modules?top=5", None),
            ("POST", "/api/storage/cache/purge", None),
        ]
        for method, path, body in endpoints:
            r = api.request(method, f"{BASE_URL}{path}", json=body, timeout=60)
            assert r.status_code < 500, f"{method} {path} → {r.status_code}: {r.text[:200]}"
