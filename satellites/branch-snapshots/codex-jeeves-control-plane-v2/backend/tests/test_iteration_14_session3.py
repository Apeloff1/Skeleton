"""
Session-3 deltas — Collections CRUD, lineage.remix_count, leaderboard.champion_weeks.
No LLM calls; fast smoke against live preview backend.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def ready_pid(s):
    """Grab a 'ready' playable id for game-attachment tests."""
    r = s.get(f"{API}/playable/list?limit=20", timeout=15)
    assert r.status_code == 200, r.text
    games = r.json().get("games") or r.json().get("playables") or []
    ready = [g for g in games if g.get("status") == "ready"]
    if not ready:
        pytest.skip("no ready playables to attach")
    return ready[0]["playable_id"]


# ── Collections CRUD ────────────────────────────────────────────────────────
class TestCollectionsCRUD:
    cid = None

    def test_01_create(self, s):
        r = s.post(f"{API}/collections", json={"name": "TEST_Session3 Coll", "description": "x"}, timeout=12)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "collection_id" in d and len(d["collection_id"]) >= 16
        assert d["name"] == "TEST_Session3 Coll"
        assert d["description"] == "x"
        assert d["game_ids"] == []
        TestCollectionsCRUD.cid = d["collection_id"]

    def test_02_list_contains(self, s):
        r = s.get(f"{API}/collections", timeout=12)
        assert r.status_code == 200
        d = r.json()
        assert "collections" in d and isinstance(d["collections"], list)
        match = [c for c in d["collections"] if c["collection_id"] == TestCollectionsCRUD.cid]
        assert match, "newly-created collection missing from list"
        c = match[0]
        assert c["count"] == 0
        assert isinstance(c.get("preview"), list)

    def test_03_add_game(self, s, ready_pid):
        r = s.post(f"{API}/collections/{TestCollectionsCRUD.cid}/games",
                   json={"playable_id": ready_pid}, timeout=12)
        assert r.status_code == 200
        d = r.json()
        assert d.get("added") is True
        assert d.get("playable_id") == ready_pid

    def test_04_add_idempotent(self, s, ready_pid):
        r = s.post(f"{API}/collections/{TestCollectionsCRUD.cid}/games",
                   json={"playable_id": ready_pid}, timeout=12)
        assert r.status_code == 200
        assert r.json().get("added") is False

    def test_05_get_hydrated(self, s, ready_pid):
        r = s.get(f"{API}/collections/{TestCollectionsCRUD.cid}", timeout=12)
        assert r.status_code == 200
        d = r.json()
        assert d["collection_id"] == TestCollectionsCRUD.cid
        assert d["count"] == 1
        assert isinstance(d["games"], list) and len(d["games"]) == 1
        g = d["games"][0]
        assert g["playable_id"] == ready_pid
        # hydrated fields
        for key in ("title", "genre", "overall", "plays"):
            assert key in g, f"missing hydrated field: {key}"

    def test_06_bad_add(self, s):
        r = s.post(f"{API}/collections/nonexistent_cid/games",
                   json={"playable_id": "x"}, timeout=12)
        assert r.status_code == 200
        assert r.json().get("error") == "collection not found"
        r2 = s.post(f"{API}/collections/{TestCollectionsCRUD.cid}/games",
                    json={"playable_id": "nonexistent_pid"}, timeout=12)
        assert r2.status_code == 200
        assert r2.json().get("error") == "game not found"

    def test_07_remove_game(self, s, ready_pid):
        r = s.delete(f"{API}/collections/{TestCollectionsCRUD.cid}/games/{ready_pid}", timeout=12)
        assert r.status_code == 200
        assert r.json().get("removed") is True
        # verify gone
        g = s.get(f"{API}/collections/{TestCollectionsCRUD.cid}", timeout=12).json()
        assert g["count"] == 0

    def test_08_delete_collection(self, s):
        r = s.delete(f"{API}/collections/{TestCollectionsCRUD.cid}", timeout=12)
        assert r.status_code == 200
        assert r.json().get("deleted") is True
        # verify gone from list
        ls = s.get(f"{API}/collections", timeout=12).json()
        assert not any(c["collection_id"] == TestCollectionsCRUD.cid for c in ls["collections"])


# ── Lineage carries remix_count on node ──────────────────────────────────────
class TestLineageRemixCount:
    def test_lineage_node_has_remix_count_field(self, s, ready_pid):
        r = s.get(f"{API}/playable/{ready_pid}/lineage", timeout=12)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "node" in d
        node = d["node"]
        # remix_count may be 0 / int; key should not error and either be absent OR int
        rc = node.get("remix_count", 0)
        assert isinstance(rc, int)
        assert rc >= 0


# ── Leaderboard exposes champion_weeks ───────────────────────────────────────
class TestLeaderboardChampionWeeks:
    def test_each_row_has_champion_weeks(self, s):
        r = s.get(f"{API}/playable/leaderboard?limit=5", timeout=15)
        assert r.status_code == 200
        d = r.json()
        rows = d.get("leaderboard", [])
        assert len(rows) > 0
        for row in rows:
            assert "champion_weeks" in row, f"row missing champion_weeks: {row.get('playable_id')}"
            assert isinstance(row["champion_weeks"], int)
            assert row["champion_weeks"] >= 0
            # also ensure pre-existing fields still there
            for k in ("remix_count", "staff_pick", "plays", "score"):
                assert k in row
