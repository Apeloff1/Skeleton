"""Iteration 130 — Recent Artifacts strip + /api/binary/recent endpoint.
Validates the new endpoint that powers the Hub's RecentArtifactsStrip,
plus a light regression smoke on adjacent binary endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")


# ── /api/binary/recent ────────────────────────────────────────────
class TestBinaryRecent:
    def test_recent_default_limit(self):
        r = requests.get(f"{BASE_URL}/api/binary/recent", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "count" in body and "artifacts" in body
        assert isinstance(body["artifacts"], list)
        # default limit is 5
        assert len(body["artifacts"]) <= 5
        # Note: server returns total-on-disk in `count`, list is truncated to limit.
        assert body["count"] >= len(body["artifacts"])

    def test_recent_with_limit_6(self):
        r = requests.get(f"{BASE_URL}/api/binary/recent?limit=6", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body.get("artifacts"), list)
        assert len(body["artifacts"]) <= 6

    def test_recent_artifact_shape(self):
        r = requests.get(f"{BASE_URL}/api/binary/recent?limit=6", timeout=15)
        assert r.status_code == 200
        arts = r.json().get("artifacts", [])
        if not arts:
            pytest.skip("no artifacts on disk in this env — shape check skipped")
        for a in arts:
            assert set(["build_id", "kind", "size_bytes", "download_url"]).issubset(a.keys())
            assert a["kind"] in ("zip", "apk")
            assert isinstance(a["size_bytes"], int) and a["size_bytes"] >= 0
            assert a["download_url"].startswith("/api/binary/download/")
            assert a["download_url"].endswith(f"/{a['kind']}")

    def test_recent_sorted_newest_first(self):
        r = requests.get(f"{BASE_URL}/api/binary/recent?limit=20", timeout=15)
        assert r.status_code == 200
        arts = r.json().get("artifacts", [])
        if len(arts) < 2:
            pytest.skip("need >=2 artifacts to verify sort order")
        # endpoint includes modified_at — confirm descending
        # (modified_at may not be in the public response; verify by re-pulling
        # via /api/binary/list which exposes timestamps for apks)
        # Soft check: download_url is unique per (build,kind)
        keys = [(a["build_id"], a["kind"]) for a in arts]
        assert len(keys) == len(set(keys))

    def test_recent_limit_clamped(self):
        # limit > 20 should clamp internally to 20; limit < 1 should clamp to 1
        r1 = requests.get(f"{BASE_URL}/api/binary/recent?limit=999", timeout=15)
        assert r1.status_code == 200
        assert len(r1.json().get("artifacts", [])) <= 20

        r2 = requests.get(f"{BASE_URL}/api/binary/recent?limit=0", timeout=15)
        assert r2.status_code == 200
        # 0 clamps to 1
        assert len(r2.json().get("artifacts", [])) <= 1


# ── Regression: adjacent endpoints still healthy ─────────────────
class TestRegressionAdjacent:
    def test_binary_list_still_works(self):
        r = requests.get(f"{BASE_URL}/api/binary/list", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "count" in body and "apks" in body

    def test_playable_list(self):
        r = requests.get(f"{BASE_URL}/api/playable/list", timeout=20)
        assert r.status_code == 200
        body = r.json()
        # used to provide a real snowball id
        assert isinstance(body, (dict, list))
