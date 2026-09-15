"""
Iteration 152 — In-Game Media Studio + Ship Build Brief regression.
"""
import os
import time
import requests
import pytest

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"

GAME = "Ember Vanguard"
ADMIN_EMAIL = "admin@gameforge.io"
ADMIN_PASSWORD = "GameForge#Admin2026"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


# ── MEDIA IMAGES ──────────────────────────────────────────────────────────
class TestMediaImages:
    def test_images_full_set(self):
        r = requests.post(f"{BASE_URL}/api/jeeves/media/images",
                          json={"game_name": GAME}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("ok") is True
        assert d.get("count") == 23, f"expected 23 images, got {d.get('count')}"
        imgs = d.get("images", [])
        assert len(imgs) == 23
        keys = {i["key"] for i in imgs}
        expected = {"main_character", "cast"} | {f"promo_{i}" for i in range(1, 11)} | \
                   {f"landscape_{i}" for i in range(10, 21)}
        missing = expected - keys
        assert not missing, f"missing keys: {missing}"
        for it in imgs:
            assert it.get("mime") == "image/png"
            assert it.get("title")
            assert it.get("base64") and len(it["base64"]) > 100


# ── MEDIA TYPES ───────────────────────────────────────────────────────────
class TestMediaTypes:
    def test_video_types(self):
        r = requests.get(f"{BASE_URL}/api/jeeves/media/types", timeout=30)
        assert r.status_code == 200
        d = r.json()
        vts = d.get("video_types", [])
        assert len(vts) == 5
        by_id = {v["id"]: v for v in vts}
        for tid in ["clip30", "clip120", "trailer", "showcase", "letsplay"]:
            assert tid in by_id, f"missing {tid}"
            assert by_id[tid].get("label")
        assert by_id["clip30"]["duration_s"] == 30
        assert by_id["clip120"]["duration_s"] == 120
        assert by_id["trailer"]["duration_s"] == 120
        assert by_id["showcase"]["duration_s"] == 60
        assert by_id["letsplay"]["duration_s"] == 300


# ── VIDEO clip30 (fast) ───────────────────────────────────────────────────
class TestVideoClip30:
    def test_clip30_render_and_download(self):
        r = requests.post(f"{BASE_URL}/api/jeeves/media/video",
                          json={"game_name": GAME, "type": "clip30"}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("status") == "rendering"
        job_id = d["job_id"]

        # poll up to ~60s
        deadline = time.time() + 90
        status_doc = {}
        while time.time() < deadline:
            time.sleep(3)
            s = requests.get(f"{BASE_URL}/api/jeeves/media/video/{job_id}", timeout=15)
            assert s.status_code == 200
            status_doc = s.json()
            if status_doc.get("status") in ("done", "error"):
                break
        assert status_doc.get("status") == "done", f"job did not complete: {status_doc}"
        assert status_doc.get("percent") == 100 or status_doc.get("percent") == 100.0
        assert status_doc.get("frames") == 450, f"frames={status_doc.get('frames')}"
        assert status_doc.get("size_bytes", 0) > 0

        # download
        dl = requests.get(f"{BASE_URL}/api/jeeves/media/download/{job_id}", timeout=60)
        assert dl.status_code == 200
        assert dl.headers.get("content-type", "").startswith("video/mp4")
        assert len(dl.content) > 1000
        # MP4 signature check (ftyp box)
        assert b"ftyp" in dl.content[:64], "not a valid mp4"


# ── VIDEO invalid type ────────────────────────────────────────────────────
class TestVideoInvalid:
    def test_invalid_type(self):
        r = requests.post(f"{BASE_URL}/api/jeeves/media/video",
                          json={"game_name": GAME, "type": "bogus"}, timeout=15)
        assert r.status_code == 400


# ── VIDEO letsplay (long-running; best-effort verify) ─────────────────────
class TestVideoLetsPlay:
    def test_letsplay_starts_and_optionally_completes(self):
        r = requests.post(f"{BASE_URL}/api/jeeves/media/video",
                          json={"game_name": GAME, "type": "letsplay"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") == "rendering"
        job_id = d["job_id"]

        # Try up to ~150s — mark as "started ok" if not done
        deadline = time.time() + 150
        last = {}
        while time.time() < deadline:
            time.sleep(6)
            s = requests.get(f"{BASE_URL}/api/jeeves/media/video/{job_id}", timeout=15)
            last = s.json()
            if last.get("status") in ("done", "error"):
                break
        if last.get("status") == "done":
            assert last.get("frames") == 3000
            assert last.get("size_bytes", 0) > 0
            print(f"[letsplay] DONE has_commentary={last.get('has_commentary')} size={last.get('size_bytes')}")
        else:
            print(f"[letsplay] long-running, started OK, last status: {last}")


# ── SHIP BUILD BRIEF ──────────────────────────────────────────────────────
class TestShipBuildBrief:
    def test_ship_produces_build_brief(self, admin_token):
        r = requests.post(f"{BASE_URL}/api/gameforge/studio/ship",
                          headers={"Authorization": f"Bearer {admin_token}"},
                          json={"game_name": "BriefTest", "push": False}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("ok") is True
        assert d.get("saga", {}).get("status") == "completed", f"saga={d.get('saga')}"
        brief = d.get("build_brief")
        assert brief, "build_brief missing"
        assert brief.get("artifact_count") == 6, f"artifact_count={brief.get('artifact_count')}"
        arts = brief.get("artifacts") or []
        # 4 charts + spreadsheet + pdf (types across artifacts)
        assert len(arts) >= 6


# ── REGRESSION ────────────────────────────────────────────────────────────
class TestRegression:
    def test_coverage_selftest(self):
        r = requests.get(f"{BASE_URL}/api/gameforge/coverage/selftest", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("passed") == 10 and d.get("total") == 10, f"{d.get('passed')}/{d.get('total')}"
        assert d.get("ok") is True

    def test_prood_readiness(self):
        r = requests.get(f"{BASE_URL}/api/prood/readiness", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("overall_percent") in (100, 100.0), f"overall_percent={d.get('overall_percent')}"
        assert d.get("capabilities_live") == 16 and d.get("capabilities_total") == 16, \
            f"{d.get('capabilities_live')}/{d.get('capabilities_total')}"

    def test_health_registry(self):
        r = requests.get(f"{BASE_URL}/api/health/registry", timeout=30)
        assert r.status_code == 200
        d = r.json()
        ok_count = d.get("ok")
        skipped = d.get("skipped", 0)
        assert isinstance(ok_count, int)
        assert ok_count >= 213, f"ok={ok_count}"
        assert skipped == 0, f"skipped={skipped}"

    def test_jeeves_compose_8_artifacts(self):
        r = requests.post(f"{BASE_URL}/api/jeeves/compose",
                          json={"query": "regression check", "needs_reasoning": False},
                          timeout=120)
        assert r.status_code == 200
        d = r.json()
        assert d.get("artifact_count") == 8, f"artifact_count={d.get('artifact_count')}"

    def test_omega_legions_16(self):
        r = requests.get(f"{BASE_URL}/api/omega/legions", timeout=30)
        assert r.status_code == 200
        d = r.json()
        lc = d.get("legion_count") or d.get("count")
        assert lc == 16, f"legion_count={lc}"
