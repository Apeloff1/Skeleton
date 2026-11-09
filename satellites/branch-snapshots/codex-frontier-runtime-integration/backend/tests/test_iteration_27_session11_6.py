"""
Session 11.6 backend tests — anti-farm rate-limit, vote claim-once, ops overview,
and stripe checkout regression. All hit the public preview URL.
"""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
READY_PID = "7b640a5ebf0c4bc0807b8640d757df76"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Anti-farm XP ──────────────────────────────────────────────────────────────
class TestAntiFarmXp:
    def test_missing_visitor_id_returns_error(self, s):
        r = s.post(f"{BASE_URL}/api/liveops/xp", json={"visitor_id": "", "action": "play"})
        assert r.status_code == 200
        assert "error" in r.json()

    def test_unknown_action_returns_error(self, s):
        r = s.post(f"{BASE_URL}/api/liveops/xp",
                   json={"visitor_id": f"farm_unknown_{int(time.time())}", "action": "no_such"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("error") == "unknown action"

    def test_burst_then_rate_limit(self, s):
        vid = f"farmtest_{int(time.time()*1000)}"
        ok_count = 0
        rl_count = 0
        for _ in range(25):
            r = s.post(f"{BASE_URL}/api/liveops/xp",
                       json={"visitor_id": vid, "action": "play"})
            assert r.status_code == 200
            body = r.json()
            if body.get("ok") is True and (body.get("gained") or 0) > 0:
                ok_count += 1
            elif body.get("error") == "rate_limited":
                rl_count += 1
        # Burst 20 — allow some slack for slow refill during execution
        assert ok_count >= 18, f"expected ~20 awards, got {ok_count}"
        assert rl_count >= 3, f"expected several rate_limited, got {rl_count}"

    def test_independent_visitor_bucket(self, s):
        vid_new = f"farmtest_other_{int(time.time()*1000)}"
        r = s.post(f"{BASE_URL}/api/liveops/xp",
                   json={"visitor_id": vid_new, "action": "play"})
        body = r.json()
        assert body.get("ok") is True
        assert (body.get("gained") or 0) > 0


# ── Anti-farm Vote ────────────────────────────────────────────────────────────
class TestAntiFarmVote:
    @pytest.fixture(scope="class")
    def tournament(self, s):
        r = s.post(f"{BASE_URL}/api/tournaments/create", json={"size": 4})
        body = r.json()
        if "error" in body:
            pytest.skip(f"cannot create tournament: {body['error']}")
        t = body["tournament"]
        return t

    def test_invalid_slot(self, s, tournament):
        tid = tournament["tournament_id"]
        mid = tournament["rounds"][0][0]["match_id"]
        r = s.post(f"{BASE_URL}/api/tournaments/{tid}/match/{mid}/vote", json={"slot": "x"})
        body = r.json()
        assert "error" in body

    def test_first_vote_ok_second_blocked(self, s, tournament):
        tid = tournament["tournament_id"]
        mid_a = tournament["rounds"][0][0]["match_id"]
        # First vote should succeed
        r1 = s.post(f"{BASE_URL}/api/tournaments/{tid}/match/{mid_a}/vote", json={"slot": "a"})
        b1 = r1.json()
        assert b1.get("ok") is True, f"unexpected first vote: {b1}"
        assert b1["votes"]["a"] >= 1
        # Second vote same match → already_voted
        r2 = s.post(f"{BASE_URL}/api/tournaments/{tid}/match/{mid_a}/vote", json={"slot": "b"})
        b2 = r2.json()
        assert b2.get("error") == "already_voted"

    def test_different_match_still_votable(self, s, tournament):
        tid = tournament["tournament_id"]
        if len(tournament["rounds"][0]) < 2:
            pytest.skip("tournament too small")
        mid_b = tournament["rounds"][0][1]["match_id"]
        r = s.post(f"{BASE_URL}/api/tournaments/{tid}/match/{mid_b}/vote", json={"slot": "a"})
        b = r.json()
        assert b.get("ok") is True
        assert b["votes"]["a"] >= 1


# ── Ops Overview ──────────────────────────────────────────────────────────────
class TestOpsOverview:
    def test_overview_open_and_shape(self, s):
        r = s.get(f"{BASE_URL}/api/admin/ops/overview")
        assert r.status_code == 200
        body = r.json()
        assert "kpis" in body and "counts" in body
        kpis = body["kpis"]
        for k in ("gmv_usd", "paid_transactions", "active_listings",
                  "live_tournaments", "creators", "games"):
            assert k in kpis, f"missing kpi {k}"
            assert isinstance(kpis[k], (int, float)), f"{k} not numeric: {kpis[k]!r}"
        counts = body["counts"]
        for c in ("playables", "playable_jobs", "marketplace_listings",
                  "marketplace_purchases", "payment_transactions",
                  "tournaments", "tournament_rewards", "liveops_progress"):
            assert c in counts, f"missing count {c}"
        assert "recent_transactions" in body and isinstance(body["recent_transactions"], list)
        assert "recent_listings" in body and isinstance(body["recent_listings"], list)
        assert "generated_at" in body
        # session_id masking — must end with '…' if present
        for t in body["recent_transactions"]:
            sid = t.get("session_id")
            if sid:
                assert sid.endswith("…"), f"session_id not masked: {sid}"


# ── Stripe regression (no completion) ────────────────────────────────────────
class TestStripeCheckoutRegression:
    def test_create_checkout_session(self, s):
        # Ensure a listing exists for the ready playable
        r_listing = s.get(f"{BASE_URL}/api/marketplace/listing/{READY_PID}")
        if r_listing.json().get("error") == "not listed":
            s.post(f"{BASE_URL}/api/marketplace/list", json={
                "playable_id": READY_PID, "price_usd": 1.99,
                "creator_id": "studioQA", "summary": "TEST"
            })
        r = s.post(f"{BASE_URL}/api/marketplace/checkout", json={
            "playable_id": READY_PID,
            "buyer_id": f"TEST_buyer_{int(time.time())}",
            "origin_url": BASE_URL,
        })
        body = r.json()
        if body.get("error") == "payments not configured":
            pytest.skip("stripe key not configured")
        assert "url" in body and body["url"].startswith("http"), f"unexpected: {body}"
        assert "session_id" in body and body["session_id"].startswith("cs_")


# ── Regression smoke ─────────────────────────────────────────────────────────
class TestRegressionSmoke:
    def test_single_xp_award_works(self, s):
        vid = f"single_xp_{int(time.time()*1000)}"
        r = s.post(f"{BASE_URL}/api/liveops/xp", json={"visitor_id": vid, "action": "play"})
        b = r.json()
        assert b.get("ok") is True
        assert (b.get("gained") or 0) > 0

    def test_liveops_pass_and_season(self, s):
        r1 = s.get(f"{BASE_URL}/api/liveops/season")
        assert r1.status_code == 200
        assert "season" in r1.json()
        r2 = s.get(f"{BASE_URL}/api/liveops/pass", params={"visitor_id": "regression_user"})
        assert r2.status_code == 200
        assert "xp" in r2.json()

    def test_marketplace_listings_and_mine(self, s):
        r1 = s.get(f"{BASE_URL}/api/marketplace/listings")
        assert r1.status_code == 200
        assert "listings" in r1.json()
        r2 = s.get(f"{BASE_URL}/api/marketplace/mine", params={"creator_id": "studioQA"})
        assert r2.status_code == 200
        assert "listings" in r2.json() and "totals" in r2.json()

    def test_marketplace_trending(self, s):
        r = s.get(f"{BASE_URL}/api/marketplace/creators/trending")
        assert r.status_code == 200
        assert "creators" in r.json()

    def test_tournaments_list(self, s):
        r = s.get(f"{BASE_URL}/api/tournaments")
        assert r.status_code == 200
        assert "tournaments" in r.json()
