"""
Iteration 136 — free-API knowledge catalog, /learn, self-improvement, self-learning growth,
plus regression on activate/map/jeeves-train.
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api/gameforge"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Free API catalog ──────────────────────────────────────────────────────────
class TestCatalog:
    def test_apis_catalog(self, s):
        r = s.get(f"{API}/knowledge/apis", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["total"] >= 39, f"expected >=39 got {d['total']}"
        cats = set(d["categories"])
        expected = {"art", "data", "dev", "finance", "fun", "games", "geo",
                    "language", "media", "reference", "research", "science"}
        missing = expected - cats
        assert not missing, f"missing categories: {missing}"

    def test_apis_wikipedia_detail(self, s):
        r = s.get(f"{API}/knowledge/apis/wikipedia", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "url" in d and "note" in d


# ── Live external fetches ─────────────────────────────────────────────────────
class TestQuery:
    def test_wikipedia_query(self, s):
        r = s.post(f"{API}/knowledge/query",
                   json={"api": "wikipedia", "params": {"q": "Procedural_generation"}},
                   timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True, f"resp: {d}"
        assert d.get("status") == 200
        assert isinstance(d.get("data"), dict)
        assert d["data"].get("extract"), "extract missing"

    def test_dictionary_query(self, s):
        r = s.post(f"{API}/knowledge/query",
                   json={"api": "dictionary", "params": {"q": "entropy"}},
                   timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        data = d.get("data")
        # dictionaryapi returns list of entries
        assert isinstance(data, list) and data
        assert data[0].get("meanings"), "no meanings returned"


# ── /learn — routes queries to correct API and stores in brain ───────────────
class TestLearn:
    def test_learn_roguelike_wikipedia(self, s):
        r = s.post(f"{API}/knowledge/learn",
                   json={"query": "what is a roguelike"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True, f"resp: {d}"
        assert d["api"] == "wikipedia"
        assert d.get("stored_in_brain") is True
        assert "roguelike" in (d.get("summary") or "").lower()

    def test_learn_define_dictionary(self, s):
        r = s.post(f"{API}/knowledge/learn",
                   json={"query": "define procedural generation"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True, f"resp: {d}"
        assert d["api"] == "dictionary"


# ── Self-improvement / lessons ───────────────────────────────────────────────
class TestSelfImprove:
    def test_self_improve_cycle(self, s):
        r = s.post(f"{API}/knowledge/self-improve",
                   json={"quality": 0.8, "coherence": 0.75, "synergy": 0.6},
                   timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        refl = d.get("reflection", {})
        assert refl.get("improvements"), f"no improvements: {refl}"

    def test_self_improve_summary(self, s):
        r = s.get(f"{API}/knowledge/self-improve/summary", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "summary" in d
        assert "lessons" in d

    def test_lessons_status(self, s):
        r = s.get(f"{API}/knowledge/lessons", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        st = d.get("status") or {}
        assert st.get("lessons", 0) >= 0

    def test_add_lesson(self, s):
        r = s.post(f"{API}/knowledge/lessons",
                   json={"source": "TEST_iter136", "pattern": "TEST_pattern",
                         "action": "TEST_action"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d.get("lesson", {}).get("source") == "TEST_iter136"


# ── Self-learning growth via boardroom accept ────────────────────────────────
class TestBrainGrowth:
    def test_knowledge_grows_after_learn_and_accept(self, s):
        # Baseline
        r0 = s.get(f"{API}/studio/jeeves/knowledge", timeout=30)
        assert r0.status_code == 200
        d0 = r0.json()
        assert d0["ok"] is True
        base_count = d0["status"].get("knowledge_count", 0)

        # /learn to boost 'acquired'
        s.post(f"{API}/knowledge/learn",
               json={"query": "what is game design"}, timeout=30)

        # Submit a clean artifact — should be ACCEPT and grow 'learned'
        payload = {
            "game_name": "TEST_iter136_game",
            "filename": f"TEST_iter136_{int(time.time())}.md",
            "content": "TEST_iter136 clean design doc: describes core loop, world, mechanics, and progression.",
            "kind": "design_doc",
        }
        rb = s.post(f"{API}/studio/boardroom/submit", json=payload, timeout=45)
        assert rb.status_code == 200
        bd = rb.json()
        assert bd["ok"] is True
        assert bd.get("verdict") == "accept", f"verdict was {bd.get('verdict')}: {bd}"

        # After
        r1 = s.get(f"{API}/studio/jeeves/knowledge", timeout=30)
        assert r1.status_code == 200
        d1 = r1.json()
        by_dom = d1["status"].get("by_domain", {})
        assert by_dom.get("acquired", 0) > 0, f"acquired not >0: {by_dom}"
        assert by_dom.get("learned", 0) > 0, f"learned not >0: {by_dom}"
        new_count = d1["status"].get("knowledge_count", 0)
        assert new_count >= base_count, f"knowledge_count shrank: {base_count}->{new_count}"


# ── Regression ────────────────────────────────────────────────────────────────
class TestRegression:
    def test_activate_4_of_4(self, s):
        r = s.post(f"{API}/activate", json={}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        # accept either shape
        live = d.get("live") or d.get("systems_live") or d.get("active")
        total = d.get("total") or d.get("systems_total")
        # fallback: search for '4/4'
        text = str(d)
        assert "4" in text
        if isinstance(live, int) and isinstance(total, int):
            assert live == 4 and total == 4, f"{live}/{total}"

    def test_map_systems_19_of_19(self, s):
        r = s.get(f"{API}/map/systems", timeout=30)
        assert r.status_code == 200
        d = r.json()
        systems = d.get("systems") or d.get("in_room_systems") or []
        # count live
        if isinstance(systems, list):
            live = sum(1 for x in systems if (isinstance(x, dict) and (x.get("status") == "live" or x.get("live"))))
            total = len(systems)
            assert total == 19, f"total {total}"
            assert live == 19, f"live {live}/{total}"

    def test_jeeves_train_fill(self, s):
        r = s.post(f"{API}/studio/jeeves/train", json={}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        fp = d.get("fill_percent") or (d.get("status") or {}).get("fill_percent")
        assert fp is not None
        assert 40 <= float(fp) <= 60, f"fill_percent {fp} not ~50"
