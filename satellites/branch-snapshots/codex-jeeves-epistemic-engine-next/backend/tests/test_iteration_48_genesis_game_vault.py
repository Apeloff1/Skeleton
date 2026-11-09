"""Iteration 48 — Asset Genesis depth additions (game-status + Vault wiring).

Validates:
 - GET /api/assets/genesis/game/{pid} ⇒ required_kinds/generated_kinds/missing/applied/tag/files/assets
 - GET /api/assets/genesis/game/<nonexistent> ⇒ {"error": "game not found"}
 - Side-effect: /api/playable/list now carries asset_status on the touched game
 - GET /api/vault/asset?tag=genesis returns assets named "<kind>: ..." w/ metadata.source=='asset_genesis'
 - Regressions: /styles still 8/8/6; /list returns {assets,count}; /{aid}.png 200; apply-assets/async ⇒ job_id;
   /api/health/registry ok=140
"""
import os, requests, pytest

BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if "EXPO_PUBLIC_BACKEND_URL" in os.environ else \
       "https://gemini-game-craft.preview.emergentagent.com"
PID = "d02790d6d8174ff59bf7005221cd7609"

@pytest.fixture(scope="session")
def s():
    sess = requests.Session(); sess.headers.update({"Content-Type": "application/json"}); return sess


# ── Genesis game-status endpoint ──────────────────────────────────────────────
class TestGenesisGameStatus:
    def test_game_status_shape(self, s):
        r = s.get(f"{BASE}/api/assets/genesis/game/{PID}", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("game_id") == PID
        assert d.get("required_kinds") == ["character", "enemy", "item", "background"]
        gens = d.get("generated_kinds") or []
        assert isinstance(gens, list) and len(gens) >= 1, f"expected non-empty generated_kinds: {gens}"
        # missing = required - generated
        missing = d.get("missing_kinds")
        assert isinstance(missing, list)
        expected_missing = [k for k in d["required_kinds"] if k not in gens]
        assert missing == expected_missing
        # tag + asset_status correlation
        assert d.get("tag"), "tag should be present"
        assert d.get("asset_status") in ("complete", "partial", "none")
        # applied — pre-applied game has has_genesis_art=True per iter47 report
        assert d.get("applied") is True, f"expected applied=True for pre-applied game; got {d.get('applied')}"
        # files: brief.txt + game.html (and possibly design_spec)
        files = d.get("files") or []
        names = [f.get("name") for f in files]
        assert "brief.txt" in names and "game.html" in names, names
        # assets array of {asset_id, kind, created_at}
        assets = d.get("assets") or []
        assert isinstance(assets, list) and len(assets) >= 1
        a0 = assets[0]
        assert "asset_id" in a0 and "kind" in a0

    def test_game_status_persists_asset_status_on_playable(self, s):
        # ensure the touch above persisted asset_status onto the playable doc
        s.get(f"{BASE}/api/assets/genesis/game/{PID}", timeout=30)
        r = s.get(f"{BASE}/api/playable/list?limit=100", timeout=30)
        assert r.status_code == 200
        pls = r.json().get("playables") or []
        match = next((p for p in pls if p.get("playable_id") == PID), None)
        assert match, "pre-applied game must be in /api/playable/list"
        assert match.get("asset_status") in ("complete", "partial", "none"), match

    def test_nonexistent_game_returns_error(self, s):
        r = s.get(f"{BASE}/api/assets/genesis/game/nonexistent_xyz_404", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("error") == "game not found"


# ── Vault wiring (mirroring) ─────────────────────────────────────────────────
class TestVaultMirror:
    def test_vault_has_genesis_assets(self, s):
        r = s.get(f"{BASE}/api/vault/asset?tag=genesis", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # accept either {assets:[...]} or list form
        assets = data.get("assets") if isinstance(data, dict) else data
        assert isinstance(assets, list) and len(assets) >= 1, f"no genesis-tagged vault assets: {data!r}"
        # at least one asset name starts with a kind label "<kind>: ..." AND metadata.source=='asset_genesis'
        kinds = ("character:", "enemy:", "item:", "background:", "tileset:", "keyart:", "icon:", "prop:")
        labeled = [a for a in assets if isinstance(a.get("name"), str) and a["name"].startswith(kinds)]
        assert labeled, f"no asset whose name starts with kind label: {[a.get('name') for a in assets[:5]]}"
        src_ok = [a for a in assets if (a.get("metadata") or {}).get("source") == "asset_genesis"]
        assert src_ok, "no vault asset has metadata.source=='asset_genesis'"


# ── Regressions ──────────────────────────────────────────────────────────────
class TestRegressions:
    def test_styles_taxonomy_8_8_6(self, s):
        r = s.get(f"{BASE}/api/assets/genesis/styles", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d.get("kinds") or []) == 8
        assert len(d.get("styles") or []) == 8
        assert len(d.get("palettes") or []) == 6

    def test_genesis_list_shape(self, s):
        r = s.get(f"{BASE}/api/assets/genesis/list?limit=10", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "assets" in d and "count" in d
        assert isinstance(d["assets"], list)

    def test_genesis_png_200(self, s):
        # pick any asset_id from the pre-applied game
        gr = s.get(f"{BASE}/api/assets/genesis/game/{PID}", timeout=20).json()
        aid = (gr.get("assets") or [{}])[0].get("asset_id")
        assert aid, "no asset_id on pre-applied game"
        r = s.get(f"{BASE}/api/assets/genesis/{aid}.png", timeout=20)
        assert r.status_code == 200
        assert (r.headers.get("content-type") or "").startswith("image/")

    def test_apply_assets_async_returns_job_id_or_known_error(self, s):
        # rate-limited / no-assets fallback is acceptable — we just need a structured response
        r = s.post(f"{BASE}/api/playable/{PID}/apply-assets/async", json={}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert ("job_id" in d) or (d.get("error") in {"rate_limited", "no generated assets linked to this game yet"}), d

    def test_health_registry_ok_140(self, s):
        r = s.get(f"{BASE}/api/health/registry", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") == 140, f"expected ok=140 got {d.get('ok')}"
