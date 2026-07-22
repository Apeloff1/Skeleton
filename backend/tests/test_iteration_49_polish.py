"""Iteration 49 — Asset Genesis polish layer.

Validates:
 - GET /api/playable/leaderboard?limit=5 → each row has 'asset_status' key
 - GET /api/playable/leaderboard?assets=complete → 200 with {count, leaderboard}
 - POST /api/playable/{pid}/apply-assets/async with {selected:{...}} body returns {job_id} (or rate_limited / no-assets)
 - POST /api/playable/{pid}/apply-assets/async with NO body still returns {job_id} (or rate_limited / no-assets)
 - GET /api/vault/asset?tag=genesis → assets[] with kind-prefixed name + metadata.source=='asset_genesis'
 - Regressions: /styles (8/8/6); /game/{pid} carries asset_status+tag; /health/registry ok=140
"""
import os, time, requests, pytest

BASE = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "https://gemini-game-craft.preview.emergentagent.com"
).rstrip("/")
PID = "d02790d6d8174ff59bf7005221cd7609"
CHAR_AID = "1f6f490c773743ceb17e32aaf7178554"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Leaderboard polish (asset_status field + assets=complete filter) ─────────
class TestLeaderboardAssetStatus:
    def test_leaderboard_rows_carry_asset_status(self, s):
        r = s.get(f"{BASE}/api/playable/leaderboard?limit=5", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "leaderboard" in d and "count" in d
        rows = d["leaderboard"]
        assert isinstance(rows, list)
        # If non-empty, every row must carry 'asset_status' key (value may be None for unmarked games)
        for row in rows:
            assert "asset_status" in row, f"row missing asset_status: {row.keys()}"
            # rank, playable_id, title sanity
            assert "rank" in row and "playable_id" in row and "title" in row

    def test_leaderboard_assets_complete_filter(self, s):
        r = s.get(f"{BASE}/api/playable/leaderboard?assets=complete", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "count" in d and "leaderboard" in d
        assert isinstance(d["leaderboard"], list)
        # if any rows returned, they must all be asset_status=='complete'
        for row in d["leaderboard"]:
            assert row.get("asset_status") == "complete", row


# ── Apply-assets selected body & no-body ─────────────────────────────────────
class TestApplyAssetsSelected:
    OK_ERRORS = {"rate_limited", "no generated assets linked to this game yet"}

    def test_apply_assets_with_selected_returns_job(self, s):
        body = {"selected": {"character": CHAR_AID}}
        r = s.post(f"{BASE}/api/playable/{PID}/apply-assets/async", json=body, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert ("job_id" in d) or (d.get("error") in self.OK_ERRORS), d

    def test_apply_assets_with_no_body_returns_job(self, s):
        # space out from prior call to keep within burst rate-limit (rate_per_sec=0.2)
        time.sleep(6)
        r = s.post(f"{BASE}/api/playable/{PID}/apply-assets/async", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert ("job_id" in d) or (d.get("error") in self.OK_ERRORS), d


# ── Vault Genesis mirror ─────────────────────────────────────────────────────
class TestVaultGenesisMirror:
    def test_vault_genesis_assets_shape(self, s):
        r = s.get(f"{BASE}/api/vault/asset?tag=genesis", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assets = data.get("assets") if isinstance(data, dict) else data
        assert isinstance(assets, list) and len(assets) >= 1, f"no genesis assets: {data!r}"
        kind_prefixes = (
            "character:", "enemy:", "item:", "background:",
            "tileset:", "keyart:", "icon:", "prop:",
        )
        labeled = [a for a in assets if isinstance(a.get("name"), str) and a["name"].startswith(kind_prefixes)]
        assert labeled, f"no asset with kind-prefixed name: {[a.get('name') for a in assets[:5]]}"
        src_ok = [a for a in assets if (a.get("metadata") or {}).get("source") == "asset_genesis"]
        assert src_ok, "no vault asset has metadata.source=='asset_genesis'"


# ── Regressions ──────────────────────────────────────────────────────────────
class TestRegressions:
    def test_genesis_styles_8_8_6(self, s):
        r = s.get(f"{BASE}/api/assets/genesis/styles", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d.get("kinds") or []) == 8
        assert len(d.get("styles") or []) == 8
        assert len(d.get("palettes") or []) == 6

    def test_genesis_game_status_has_tag_and_status(self, s):
        r = s.get(f"{BASE}/api/assets/genesis/game/{PID}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("tag"), "tag missing"
        assert d.get("asset_status") in ("complete", "partial", "none")

    def test_health_registry_ok_140(self, s):
        r = s.get(f"{BASE}/api/health/registry", timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") == 140
