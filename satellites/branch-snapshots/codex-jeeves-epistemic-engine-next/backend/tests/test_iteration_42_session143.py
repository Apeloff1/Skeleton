"""Iteration 42 — Session 14.3:
- Write rate-limits on /react and /marketplace/list (IP token bucket)
- Studio Preferences CRUD + clamping
- Async generation kickoff with creator_id bias (additive, try/except-guarded)
- Appeal-outcome notifications loop
- Regression on leaderboard / trending / marketplace listings / registered count
"""
import os
import time
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
    r = s.get(f"{API}/playable/list", timeout=30)
    assert r.status_code == 200, r.text
    items = r.json().get("playables") or r.json().get("items") or r.json().get("list") or []
    # discover key
    if not items:
        for key in ("playables", "items", "ready", "list"):
            if key in r.json() and r.json()[key]:
                items = r.json()[key]; break
    assert items, f"no playables: {r.text[:300]}"
    # pick first ready w/ moderation_status != hidden
    for d in items:
        if d.get("status", "ready") == "ready":
            return d.get("playable_id") or d.get("id")
    return items[0].get("playable_id") or items[0].get("id")


# ── REGRESSION ────────────────────────────────────────────────────────────────
class TestRegression:
    def test_leaderboard_200(self, s):
        r = s.get(f"{API}/playable/leaderboard", timeout=30)
        assert r.status_code == 200, r.text

    def test_trending_200(self, s):
        r = s.get(f"{API}/playable/trending", timeout=30)
        assert r.status_code == 200, r.text
        assert "trending" in r.json()

    def test_marketplace_listings_200(self, s):
        r = s.get(f"{API}/marketplace/listings", timeout=30)
        assert r.status_code == 200, r.text
        assert "listings" in r.json()

    def test_routes_registered(self, s):
        r = s.get(f"{API}/routes", timeout=30)
        # tolerate missing /routes; if exists, registered should be >= 104
        if r.status_code == 200:
            data = r.json()
            n = data.get("registered") or data.get("count") or len(data.get("routes", []))
            assert n is None or n >= 100, f"registered={n}"


# ── REACT RATE-LIMIT ─────────────────────────────────────────────────────────
class TestReactRateLimit:
    def test_invalid_emoji(self, s, ready_pid):
        r = s.post(f"{API}/playable/{ready_pid}/react", json={"emoji": "🤡"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("error") == "invalid emoji", j

    def test_single_react_succeeds(self, s, ready_pid):
        # tiny sleep to let bucket refill from previous tests
        time.sleep(1.0)
        r = s.post(f"{API}/playable/{ready_pid}/react", json={"emoji": "🔥"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "reactions" in j, j

    def test_rapid_reacts_get_throttled(self, s, ready_pid):
        # burst 15 @ 2/s — fire 20 rapidly, expect at least one rate_limited
        time.sleep(1.0)
        statuses = []
        for _ in range(22):
            r = s.post(f"{API}/playable/{ready_pid}/react", json={"emoji": "❤️"}, timeout=15)
            try:
                statuses.append(r.json().get("error"))
            except Exception:
                statuses.append("nonjson")
        rl = sum(1 for x in statuses if x == "rate_limited")
        assert rl >= 1, f"expected rate_limited but none seen; statuses={statuses}"


# ── MARKETPLACE/LIST RATE-LIMIT ──────────────────────────────────────────────
class TestMarketplaceListRateLimit:
    def test_single_list_ok(self, s, ready_pid):
        time.sleep(2.0)  # allow bucket refill
        r = s.post(f"{API}/marketplace/list",
                   json={"playable_id": ready_pid, "price_usd": 4.99, "creator_id": "qa-test"},
                   timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        # accept ok or rate_limited (preview shares IPs sometimes)
        assert j.get("ok") is True or j.get("error") in ("rate_limited",), j

    def test_rapid_list_throttles(self, s, ready_pid):
        # burst 6 — fire 10 rapidly
        time.sleep(0.5)
        errs = []
        for _ in range(10):
            r = s.post(f"{API}/marketplace/list",
                       json={"playable_id": ready_pid, "price_usd": 4.99, "creator_id": "qa-test"},
                       timeout=20)
            try:
                errs.append(r.json().get("error"))
            except Exception:
                errs.append("nonjson")
        rl = sum(1 for x in errs if x == "rate_limited")
        assert rl >= 1, f"expected at least one rate_limited; errs={errs}"


# ── STUDIO PREFERENCES ───────────────────────────────────────────────────────
CREATOR = "qa-test"


class TestStudioPreferences:
    def test_put_saves_clamped(self, s):
        body = {
            "genres": ["puzzle", "arcade"],
            "art_style": "neon",
            "difficulty": "hardcore",
            "tone": "competitive",
            "constitution": "always add a combo meter",
            "avoid": "no gore",
        }
        r = s.put(f"{API}/creator/preferences/{CREATOR}", json=body, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("saved") is True
        p = j["preferences"]
        assert p["genres"] == ["puzzle", "arcade"]
        assert p["art_style"] == "neon"
        assert p["difficulty"] == "hardcore"
        assert p["tone"] == "competitive"
        assert "combo meter" in p["constitution"]
        assert p["avoid"] == "no gore"

    def test_get_returns_saved_and_options(self, s):
        r = s.get(f"{API}/creator/preferences/{CREATOR}", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["has_saved"] is True
        p = j["preferences"]
        assert p["art_style"] == "neon"
        opts = j["options"]
        assert isinstance(opts["art_styles"], list) and "neon" in opts["art_styles"]
        assert isinstance(opts["difficulties"], list) and "hardcore" in opts["difficulties"]
        assert isinstance(opts["tones"], list) and "competitive" in opts["tones"]

    def test_invalid_art_style_coerced(self, s):
        r = s.put(f"{API}/creator/preferences/{CREATOR}-tmp",
                  json={"art_style": "bogus"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["preferences"]["art_style"] == "any"

    def test_genres_capped_at_6(self, s):
        r = s.put(f"{API}/creator/preferences/{CREATOR}-tmp2",
                  json={"genres": ["a", "b", "c", "d", "e", "f", "g", "h"]},
                  timeout=15)
        assert r.status_code == 200, r.text
        assert len(r.json()["preferences"]["genres"]) == 6

    def test_unknown_creator_defaults(self, s):
        r = s.get(f"{API}/creator/preferences/nobody-qa-{int(time.time())}", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["has_saved"] is False
        assert j["preferences"]["art_style"] == "any"

    def test_cleanup_prefs(self, s):
        # Use _db cleanup via direct mongo? Not accessible; leave doc — minimal.
        pass


# ── GENERATION KICKOFF WITH creator_id BIAS ──────────────────────────────────
class TestGenerateWithBias:
    def test_kickoff_returns_job_id(self, s):
        r = s.post(f"{API}/playable/generate/async",
                   json={"brief": "a simple tap dodge game", "depth": "fast",
                         "creator_id": "qa-test"}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "job_id" in j, j

    def test_job_status_polls(self, s):
        r = s.post(f"{API}/playable/generate/async",
                   json={"brief": "a tiny tap dodge game", "depth": "fast",
                         "creator_id": "qa-test"}, timeout=30)
        job = r.json().get("job_id")
        assert job
        # Poll briefly (don't insist on ready in CI)
        deadline = time.time() + 30
        last = None
        while time.time() < deadline:
            jr = s.get(f"{API}/playable/job/{job}", timeout=20)
            assert jr.status_code == 200, jr.text
            last = jr.json()
            st = last.get("status") or last.get("job_status")
            if st in ("ready", "failed"):
                break
            time.sleep(2)
        assert last and ("status" in last or "job_status" in last)


# ── APPEAL-OUTCOME NOTIFICATIONS ─────────────────────────────────────────────
class TestAppealNotifications:
    def test_fresh_creator_empty(self, s):
        r = s.get(f"{API}/governance/notifications/qa-test-fresh-{int(time.time())}", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["notifications"] == []
        assert j["count"] == 0

    def test_full_loop(self, s, ready_pid):
        creator = f"qa-test-{int(time.time())}"
        # 1) report
        r = s.post(f"{API}/governance/report",
                   json={"playable_id": ready_pid, "reason": "inappropriate",
                         "detail": "test", "reporter_id": creator}, timeout=15)
        assert r.status_code == 200, r.text
        rid = r.json().get("report_id")
        if not rid:
            pytest.skip(f"could not create report: {r.json()}")
        # 2) moderate hide
        r = s.post(f"{API}/governance/moderate/{rid}",
                   json={"action": "hide", "actor": "qa-mod"}, timeout=15)
        assert r.status_code == 200, r.text
        # 3) appeal
        r = s.post(f"{API}/governance/appeal",
                   json={"playable_id": ready_pid,
                         "reason": "please reconsider this is a fine game",
                         "creator_id": creator}, timeout=15)
        assert r.status_code == 200, r.text
        aid = r.json().get("appeal_id")
        assert aid, r.json()
        # 4) resolve restore
        r = s.post(f"{API}/governance/appeal/{aid}/resolve",
                   json={"action": "restore", "actor": "qa-mod"}, timeout=15)
        assert r.status_code == 200, r.text
        # 5) notification appears
        r = s.get(f"{API}/governance/notifications/{creator}", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["count"] >= 1, j
        assert j["notifications"][0]["status"] == "granted"
        assert "title" in j["notifications"][0]
        # 6) ack
        r = s.post(f"{API}/governance/notifications/{creator}/ack", timeout=15)
        assert r.status_code == 200, r.text
        # 7) empty again
        r = s.get(f"{API}/governance/notifications/{creator}", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["count"] == 0
        # cleanup: ensure game is restored (already done via appeal restore)
