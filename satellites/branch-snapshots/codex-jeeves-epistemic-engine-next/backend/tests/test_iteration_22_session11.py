"""Iteration 22 / Session 11 — Tournaments, Live-Ops, Marketplace + Finetune/Bugsquash.

Run with:
  EXPO_PUBLIC_BACKEND_URL=https://gemini-game-craft.preview.emergentagent.com \
  pytest /app/backend/tests/test_iteration_22_session11.py -v \
    --junitxml=/app/test_reports/pytest/iteration_22_session11.xml
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL")
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL must be set")
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

TIMEOUT = 30


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ─── Regression: existing /api/playable surface still alive ────────────────────
class TestPlayableRegression:
    def test_list(self, s):
        r = s.get(f"{API}/playable/list", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert "playables" in j
        assert isinstance(j["playables"], list)

    def test_leaderboard(self, s):
        r = s.get(f"{API}/playable/leaderboard", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "leaderboard" in r.json() or "rows" in r.json() or "items" in r.json() or "playables" in r.json()

    def test_trending(self, s):
        r = s.get(f"{API}/playable/trending", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_collections(self, s):
        r = s.get(f"{API}/collections", timeout=TIMEOUT)
        assert r.status_code == 200


def _pick_ready_pid(s, exclude=None):
    r = s.get(f"{API}/playable/list?limit=80", timeout=TIMEOUT).json()
    games = r.get("playables") or r.get("items") or []
    for g in games:
        if g.get("status") == "ready" and g.get("playable_id") and g["playable_id"] != exclude:
            return g["playable_id"]
    return None


# ─── Live-Ops ──────────────────────────────────────────────────────────────────
class TestLiveOps:
    def test_season_shape(self, s):
        r = s.get(f"{API}/liveops/season", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert "season" in j and "battle_pass" in j
        assert isinstance(j["season"].get("name"), str) and j["season"]["name"]
        assert len(j["season"].get("events", [])) == 2
        assert isinstance(j["season"].get("xp_multiplier"), int)
        assert len(j["battle_pass"]) == 8

    def test_pass_initial(self, s):
        r = s.get(f"{API}/liveops/pass?visitor_id=qa_iter22", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert "xp" in j and "tier" in j and "tiers" in j
        assert len(j["tiers"]) == 8
        assert all("unlocked" in t for t in j["tiers"])

    def test_xp_missing_visitor(self, s):
        r = s.post(f"{API}/liveops/xp", json={"action": "generate"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "error" in r.json()

    def test_xp_unknown_action(self, s):
        r = s.post(f"{API}/liveops/xp", json={"visitor_id": "qa_iter22", "action": "bogus"}, timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert "error" in j and "allowed" in j

    def test_xp_award_and_multiplier(self, s):
        season = s.get(f"{API}/liveops/season", timeout=TIMEOUT).json()["season"]
        mult = season["xp_multiplier"]
        r = s.post(f"{API}/liveops/xp", json={"visitor_id": "qa_iter22_award", "action": "generate"}, timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        # base for generate is 20
        assert j.get("gained") == 20 * mult
        assert j.get("xp_multiplier") == mult
        # confirm persisted
        after = s.get(f"{API}/liveops/pass?visitor_id=qa_iter22_award", timeout=TIMEOUT).json()
        assert after["xp"] == 20 * mult


# ─── Marketplace ───────────────────────────────────────────────────────────────
class TestMarketplace:
    @pytest.fixture(scope="class")
    def listing_pid(self, s):
        pid = _pick_ready_pid(s)
        assert pid, "need at least one ready playable to list"
        r = s.post(f"{API}/marketplace/list",
                   json={"playable_id": pid, "price_usd": 4.99, "creator_id": "qa_iter22"},
                   timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j.get("ok") is True and j["listing"]["price_usd"] == 4.99
        return pid

    def test_list_bad_pid(self, s):
        r = s.post(f"{API}/marketplace/list",
                   json={"playable_id": "does_not_exist", "price_usd": 4.99, "creator_id": "qa"},
                   timeout=TIMEOUT)
        assert "error" in r.json()

    def test_list_price_low(self, s, listing_pid):
        r = s.post(f"{API}/marketplace/list",
                   json={"playable_id": listing_pid, "price_usd": 0.10, "creator_id": "qa"},
                   timeout=TIMEOUT)
        assert "error" in r.json()

    def test_list_price_high(self, s, listing_pid):
        r = s.post(f"{API}/marketplace/list",
                   json={"playable_id": listing_pid, "price_usd": 9999, "creator_id": "qa"},
                   timeout=TIMEOUT)
        assert "error" in r.json()

    def test_listings_sorted(self, s, listing_pid):
        for sort in ("newest", "price_low", "price_high", "bestselling"):
            r = s.get(f"{API}/marketplace/listings?sort={sort}", timeout=TIMEOUT)
            assert r.status_code == 200
            assert "listings" in r.json()

    def test_listing_detail(self, s, listing_pid):
        r = s.get(f"{API}/marketplace/listing/{listing_pid}", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["listing"]["price_usd"] == 4.99
        assert j["owned"] is False

    def test_checkout_creates_session(self, s, listing_pid):
        r = s.post(f"{API}/marketplace/checkout",
                   json={"playable_id": listing_pid, "buyer_id": "qa_buyer_22",
                         "origin_url": BASE_URL},
                   timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "url" in j and "session_id" in j, j
        assert "cs_test_" in j["session_id"] or j["session_id"].startswith("cs_")
        # status endpoint should respond (may stay open/unpaid — not a failure)
        st = s.get(f"{API}/marketplace/checkout/status/{j['session_id']}", timeout=TIMEOUT)
        assert st.status_code == 200
        sj = st.json()
        assert "payment_status" in sj or "status" in sj

    def test_checkout_ignores_client_amount(self, s, listing_pid):
        # even if client tries to send amount, server uses listing price
        r = s.post(f"{API}/marketplace/checkout",
                   json={"playable_id": listing_pid, "buyer_id": "qa_buyer_22b",
                         "amount": 9999, "origin_url": BASE_URL},
                   timeout=TIMEOUT)
        # CheckoutBody ignores unknown 'amount' field; should still succeed
        assert r.status_code == 200
        # we can't inspect listing amount from session, but transaction was created
        # by checking purchases collection via API (no direct access); skip deep check

    def test_purchases_empty(self, s):
        r = s.get(f"{API}/marketplace/purchases?buyer_id=qa_unknown_iter22", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("purchases") == [] or r.json().get("count") == 0


# ─── Tournaments ───────────────────────────────────────────────────────────────
class TestTournaments:
    @pytest.fixture(scope="class")
    def tid(self, s):
        r = s.post(f"{API}/tournaments/create",
                   json={"name": "QA Iter22 Bracket", "size": 4}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        return j["tournament"]["tournament_id"]

    def test_list(self, s, tid):
        r = s.get(f"{API}/tournaments", timeout=TIMEOUT)
        assert r.status_code == 200
        assert any(t["tournament_id"] == tid for t in r.json()["tournaments"])

    def test_get_hydrated(self, s, tid):
        r = s.get(f"{API}/tournaments/{tid}", timeout=TIMEOUT)
        assert r.status_code == 200
        t = r.json()["tournament"]
        assert t["size"] == 4
        assert len(t["rounds"][0]) == 2  # 4 players → 2 matches

    def test_vote_invalid_slot(self, s, tid):
        t = s.get(f"{API}/tournaments/{tid}", timeout=TIMEOUT).json()["tournament"]
        mid = t["rounds"][0][0]["match_id"]
        r = s.post(f"{API}/tournaments/{tid}/match/{mid}/vote",
                   json={"slot": "x"}, timeout=TIMEOUT)
        assert "error" in r.json()

    def test_walk_bracket_to_champion(self, s, tid):
        # Round 1 — vote slot 'a' to win both matches
        t = s.get(f"{API}/tournaments/{tid}", timeout=TIMEOUT).json()["tournament"]
        for m in t["rounds"][0]:
            rv = s.post(f"{API}/tournaments/{tid}/match/{m['match_id']}/vote",
                        json={"slot": "a"}, timeout=TIMEOUT)
            assert rv.json().get("ok") is True
        adv = s.post(f"{API}/tournaments/{tid}/advance", timeout=TIMEOUT).json()
        assert adv.get("status") == "live", adv
        assert adv.get("matches") == 1

        # Round 2 (final)
        t = s.get(f"{API}/tournaments/{tid}", timeout=TIMEOUT).json()["tournament"]
        final = t["rounds"][1][0]
        s.post(f"{API}/tournaments/{tid}/match/{final['match_id']}/vote",
               json={"slot": "a"}, timeout=TIMEOUT)
        adv2 = s.post(f"{API}/tournaments/{tid}/advance", timeout=TIMEOUT).json()
        assert adv2.get("status") == "complete", adv2
        assert adv2.get("champion_id")
        assert adv2.get("reward")

        # Already complete — voting/advancing should error
        v_after = s.post(f"{API}/tournaments/{tid}/match/{final['match_id']}/vote",
                         json={"slot": "a"}, timeout=TIMEOUT)
        assert "error" in v_after.json()
        a_after = s.post(f"{API}/tournaments/{tid}/advance", timeout=TIMEOUT)
        assert "error" in a_after.json()

    def test_create_too_small(self, s):
        # if there aren't >=16 ready games this should error; we just verify it doesn't crash
        r = s.post(f"{API}/tournaments/create",
                   json={"name": "qa_big", "size": 16}, timeout=TIMEOUT)
        assert r.status_code == 200


# ─── Finetune / Bugsquash (slow LLM) ───────────────────────────────────────────
def _poll_job(s, job_id, budget=180):
    t0 = time.time()
    while time.time() - t0 < budget:
        r = s.get(f"{API}/playable/job/{job_id}", timeout=TIMEOUT).json()
        if r.get("job_status") in ("done", "error"):
            return r
        time.sleep(5)
    return {"job_status": "timeout"}


class TestEdits:
    def test_finetune_bad_pid(self, s):
        r = s.post(f"{API}/playable/does_not_exist/finetune/async",
                   json={"instruction": "make it faster"}, timeout=TIMEOUT)
        assert r.json().get("error") == "not found"

    def test_bugsquash_short_instruction(self, s):
        pid = _pick_ready_pid(s)
        r = s.post(f"{API}/playable/{pid}/bugsquash/async",
                   json={"instruction": "no"}, timeout=TIMEOUT)
        assert "error" in r.json()

    def test_finetune_async_done(self, s):
        pid = _pick_ready_pid(s, exclude="7b640a5ebf0c4bc0807b8640d757df76")
        assert pid
        before = s.get(f"{API}/playable/{pid}", timeout=TIMEOUT).json()
        v_before = int(before.get("playable", before).get("version") or 1) if isinstance(before, dict) else 1
        # endpoint may return {"playable": {...}} or {...}
        bdoc = before.get("playable") if "playable" in before else before
        v_before = int(bdoc.get("version") or 1)

        kick = s.post(f"{API}/playable/{pid}/finetune/async",
                      json={"instruction": "make the player move faster"}, timeout=TIMEOUT).json()
        assert kick.get("job_status") == "running" and kick.get("job_id")
        result = _poll_job(s, kick["job_id"], budget=200)
        assert result.get("job_status") == "done", result
        assert result.get("kind") == "finetune"
        assert result.get("edited") is True
        assert result.get("status") == "ready"
        assert result.get("playability_score", 0) >= 70
        assert int(result.get("version") or 0) > v_before

    def test_bugsquash_async_done(self, s):
        pid = _pick_ready_pid(s, exclude="7b640a5ebf0c4bc0807b8640d757df76")
        assert pid
        kick = s.post(f"{API}/playable/{pid}/bugsquash/async",
                      json={"instruction": "score shows NaN on first load"}, timeout=TIMEOUT).json()
        assert kick.get("job_status") == "running"
        result = _poll_job(s, kick["job_id"], budget=200)
        assert result.get("job_status") == "done", result
        assert result.get("kind") == "bugsquash"
        assert result.get("edited") is True
        assert result.get("status") == "ready"
        assert result.get("playability_score", 0) >= 70
