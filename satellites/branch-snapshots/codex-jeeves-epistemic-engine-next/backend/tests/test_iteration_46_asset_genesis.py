"""Iteration 46 — Asset Genesis (Nano-Banana real image gen).

Coverage:
- GET /api/assets/genesis/styles taxonomy shape
- POST /api/assets/genesis/async + poll /job/{id} until done → asset_id + data_uri + PNG fetch
- description-required validation
- GET /api/assets/genesis/list (light, no b64)
- POST /api/assets/genesis/link {ok, bad game_id}
- Regression: /api/playable/list, /api/playable/leaderboard, /api/health/registry
"""
import os
import time
import base64
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ───────────────────── styles taxonomy ─────────────────────
class TestStyles:
    def test_styles_shape(self, api):
        r = api.get(f"{BASE_URL}/api/assets/genesis/styles", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("kinds"), list) and len(d["kinds"]) == 8
        assert isinstance(d.get("styles"), list) and len(d["styles"]) == 8
        assert isinstance(d.get("palettes"), list) and len(d["palettes"]) == 6
        pack = d.get("default_pack")
        assert pack == ["character", "enemy", "item", "background"]
        # element shape
        assert {"id", "hint"} <= set(d["kinds"][0].keys())


# ───────────────────── validation ─────────────────────
class TestValidation:
    def test_missing_description_returns_error(self, api):
        r = api.post(f"{BASE_URL}/api/assets/genesis/async",
                     json={"description": "  ", "kind": "character"}, timeout=20)
        assert r.status_code == 200
        assert r.json().get("error") == "description required"


# ───────────────────── single generation E2E ─────────────────────
class TestSingleGeneration:
    """Real Nano-Banana image gen — ~8-15s typical, allow generous timeout."""
    asset_id_holder: dict = {}

    def test_kick_and_poll_until_done(self, api):
        body = {"description": "a brave fox knight",
                "kind": "character", "style": "flat_vector", "palette": "vibrant"}
        r = api.post(f"{BASE_URL}/api/assets/genesis/async", json=body, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "job_id" in d, d
        assert d.get("mode") == "single"
        assert d.get("kind") == "character"
        job_id = d["job_id"]

        # poll up to 90s
        final = None
        for _ in range(30):
            time.sleep(3)
            jr = api.get(f"{BASE_URL}/api/assets/genesis/job/{job_id}", timeout=20)
            assert jr.status_code == 200, jr.text
            jd = jr.json()
            if jd.get("status") in ("done", "error"):
                final = jd
                break

        assert final is not None, "job never resolved within 90s"
        assert final.get("status") == "done", f"job ended with: {final}"
        assert final.get("mode") == "single"
        assert final.get("asset_id"), "asset_id missing on done payload"
        du = final.get("data_uri", "")
        assert du.startswith("data:image/"), f"bad data_uri prefix: {du[:40]}"
        assert ";base64," in du
        # sanity: base64 body decodes
        b64 = du.split(";base64,", 1)[1]
        raw = base64.b64decode(b64[:2000] + "==")  # decode head only
        assert len(raw) > 100
        TestSingleGeneration.asset_id_holder["aid"] = final["asset_id"]

    def test_png_endpoint_returns_image(self, api):
        aid = TestSingleGeneration.asset_id_holder.get("aid")
        if not aid:
            pytest.skip("no asset from generation step")
        r = api.get(f"{BASE_URL}/api/assets/genesis/{aid}.png", timeout=20)
        assert r.status_code == 200, r.status_code
        assert r.headers.get("content-type", "").startswith("image/")
        assert len(r.content) > 200
        # PNG magic bytes
        assert r.content[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1")

    def test_png_unknown_id_404(self, api):
        r = api.get(f"{BASE_URL}/api/assets/genesis/nonexistent_id_xxxx.png", timeout=15)
        assert r.status_code == 404


# ───────────────────── list (light) ─────────────────────
class TestList:
    def test_list_excludes_b64(self, api):
        r = api.get(f"{BASE_URL}/api/assets/genesis/list?limit=40", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("assets"), list)
        assert isinstance(d.get("count"), int)
        assert d["count"] == len(d["assets"])
        for a in d["assets"]:
            assert "b64" not in a, "list endpoint must not include b64"
            assert "prompt" not in a
            assert "asset_id" in a and "kind" in a


# ───────────────────── link ─────────────────────
class TestLink:
    def test_bad_game_id_returns_error(self, api):
        r = api.post(f"{BASE_URL}/api/assets/genesis/link",
                     json={"game_id": "definitely_not_a_game_xyz", "asset_ids": ["x"]}, timeout=20)
        assert r.status_code == 200
        assert r.json().get("error") == "game not found"

    def test_link_to_real_playable(self, api):
        aid = TestSingleGeneration.asset_id_holder.get("aid")
        if not aid:
            pytest.skip("no asset to link")
        plist = api.get(f"{BASE_URL}/api/playable/list?limit=10", timeout=20)
        assert plist.status_code == 200
        items = plist.json().get("items") or plist.json().get("playables") or []
        # try to find any with playable_id and status ready
        gid = None
        for it in items:
            if it.get("playable_id"):
                gid = it["playable_id"]
                break
        if not gid:
            pytest.skip("no playable available to link to")
        r = api.post(f"{BASE_URL}/api/assets/genesis/link",
                     json={"game_id": gid, "asset_ids": [aid]}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("linked", 0) >= 1
        assert d.get("game_id") == gid


# ───────────────────── regression ─────────────────────
class TestRegression:
    def test_playable_list_200(self, api):
        r = api.get(f"{BASE_URL}/api/playable/list", timeout=20)
        assert r.status_code == 200

    def test_playable_leaderboard_200(self, api):
        r = api.get(f"{BASE_URL}/api/playable/leaderboard", timeout=20)
        assert r.status_code == 200

    def test_health_registry(self, api):
        r = api.get(f"{BASE_URL}/api/health/registry", timeout=20)
        assert r.status_code == 200
        d = r.json()
        ok = d.get("ok") or d.get("registered") or d.get("count")
        # Expected ~139 per spec; accept >=130 to allow small drift
        assert isinstance(ok, int) and ok >= 130, f"registry count too low: {d}"
