"""
Iteration 68 — V.4 Multiplayer/Netcode Scaffold Studio backend tests.

Covers:
- GET /api/multiplayer/models — 4 models with required fields
- GET /api/multiplayer/models?genre=... — recommended per-genre
- GET /api/multiplayer/recommend — model object returned
- POST /api/multiplayer/scaffold — generates 5 files w/ content; respects model/max_players
- POST → GET /api/multiplayer/scaffold/{pid} round-trip
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


REQUIRED_MODEL_KEYS = {"id", "label", "desc", "best_for", "tradeoffs", "recommended_tick"}
EXPECTED_IDS = {"authoritative", "rollback", "lockstep", "relay"}


# ── 1) GET /api/multiplayer/models — list all 4 models ──────────────────────
class TestListModels:
    def test_list_all_models(self, s):
        r = s.get(f"{BASE_URL}/api/multiplayer/models", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        models = data.get("models")
        assert isinstance(models, list)
        ids = {m["id"] for m in models}
        assert ids == EXPECTED_IDS, f"Expected {EXPECTED_IDS}, got {ids}"
        # Validate every model has the required fields
        for m in models:
            assert REQUIRED_MODEL_KEYS.issubset(m.keys()), f"missing keys in {m}"
            assert isinstance(m["best_for"], list) and len(m["best_for"]) > 0
            assert isinstance(m["recommended_tick"], int) and m["recommended_tick"] > 0
            assert isinstance(m["label"], str) and m["label"]
            assert isinstance(m["desc"], str) and m["desc"]
            assert isinstance(m["tradeoffs"], str) and m["tradeoffs"]

    @pytest.mark.parametrize("genre,expected", [
        ("fighting", "rollback"),
        ("rts", "lockstep"),
        ("turn-based", "relay"),
        ("co-op", "authoritative"),
    ])
    def test_models_genre_recommend(self, s, genre, expected):
        r = s.get(f"{BASE_URL}/api/multiplayer/models", params={"genre": genre}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("recommended") == expected, f"genre={genre} got {data.get('recommended')}"


# ── 2) GET /api/multiplayer/recommend ───────────────────────────────────────
class TestRecommend:
    def test_recommend_racing(self, s):
        r = s.get(f"{BASE_URL}/api/multiplayer/recommend", params={"genre": "racing"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "recommended" in data and data["recommended"] in EXPECTED_IDS
        assert "model" in data and data["model"].get("id") == data["recommended"]
        # racing maps to rollback (per best_for list)
        assert data["recommended"] == "rollback"
        m = data["model"]
        assert REQUIRED_MODEL_KEYS.issubset(m.keys())


# ── 3) POST /api/multiplayer/scaffold ───────────────────────────────────────
EXPECTED_PATHS = {"server/index.js", "server/lobby.js", "shared/protocol.ts",
                  "client/netClient.ts", "README.md"}


class TestScaffold:
    def test_scaffold_skybreakers_arena(self, s):
        body = {"game": "Skybreakers", "genre": "fast-pvp arena", "max_players": 8}
        r = s.post(f"{BASE_URL}/api/multiplayer/scaffold", json=body, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["model"] == "rollback", f"expected rollback, got {d['model']}"
        assert d["file_count"] == 5
        assert d["max_players"] == 8
        assert d["tick_rate"] == 60
        assert d["snapshot_rate"] <= d["tick_rate"]
        files = d["files"]
        paths = {f["path"] for f in files}
        assert paths == EXPECTED_PATHS, f"got {paths}"
        # Every file has non-empty content
        for f in files:
            assert isinstance(f["content"], str) and len(f["content"]) > 50, f"empty file {f['path']}"
            assert f.get("lang"), f"missing lang for {f['path']}"

    def test_scaffold_respects_explicit_model_and_players(self, s):
        body = {"game": "Empire", "genre": "rts", "model": "lockstep", "max_players": 32}
        r = s.post(f"{BASE_URL}/api/multiplayer/scaffold", json=body, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["model"] == "lockstep"
        assert d["max_players"] == 32
        assert d["file_count"] == 5

    def test_scaffold_pid_persistence_roundtrip(self, s):
        pid = f"TEST_mp_{uuid.uuid4().hex[:8]}"
        body = {"pid": pid, "game": "TEST_Persist", "genre": "co-op", "max_players": 4}
        post = s.post(f"{BASE_URL}/api/multiplayer/scaffold", json=body, timeout=30)
        assert post.status_code == 200, post.text
        posted = post.json()
        # default genre co-op → authoritative
        assert posted["model"] == "authoritative"

        get = s.get(f"{BASE_URL}/api/multiplayer/scaffold/{pid}", timeout=30)
        assert get.status_code == 200, get.text
        stored = get.json()
        assert stored.get("pid") == pid
        assert stored.get("model") == "authoritative"
        assert stored.get("max_players") == 4
        # Files persisted
        assert isinstance(stored.get("files"), list) and len(stored["files"]) == 5
        # MongoDB _id must be excluded
        assert "_id" not in stored

    def test_scaffold_get_missing_pid_404(self, s):
        r = s.get(f"{BASE_URL}/api/multiplayer/scaffold/TEST_does_not_exist_{uuid.uuid4().hex[:6]}", timeout=30)
        assert r.status_code == 404


# ── 4) Voiced-trailer endpoint smoke test (used by gallery Trailer button) ──
class TestJeevesTrailer:
    def test_trailer_endpoint(self, s):
        body = {"pid": "TEST_trailer_pid", "title": "Skybreakers", "genre": "arena", "lore": "A neon arena."}
        r = s.post(f"{BASE_URL}/api/jeeves-voice/trailer", json=body, timeout=60)
        # Endpoint must respond OK (200) and not crash; payload shape varies
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
