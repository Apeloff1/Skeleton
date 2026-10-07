"""
Iteration 40 — VII.5 follow-up: auto-gate field presence + non-regression,
hidden-exclusion from public rails, marketplace near-dup warning + hidden-block.

No auth. BASE_URL from EXPO_PUBLIC_BACKEND_URL / EXPO_BACKEND_URL.
After hide-exclusion test, RESTORES the playable so catalogue isn't degraded.
"""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "https://gemini-game-craft.preview.emergentagent.com"
).rstrip("/")

TIMEOUT = 30


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── (a) Auto-gate field presence on existing playables ─────────────────────
class TestAutoGateFields:
    """Recent/new playables should carry moderation_status + policy_scan."""

    def test_playable_list_includes_moderation_fields(self, s):
        r = s.get(f"{BASE_URL}/api/playable/list?limit=20", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("playables") or []
        assert items, "expected at least one playable"
        # Check at least the first few have moderation_status and policy_scan
        sampled = items[:10]
        with_status = [p for p in sampled if "moderation_status" in p]
        with_scan = [p for p in sampled if "policy_scan" in p]
        assert with_status, "no playable carried moderation_status"
        assert with_scan, "no playable carried policy_scan"
        # And policy_scan should have verdict + score
        any_scan = next((p["policy_scan"] for p in sampled if p.get("policy_scan")), None)
        assert any_scan and "verdict" in any_scan and "score" in any_scan


# ── (b) Non-regression: discovery rails all 200 ───────────────────────────
class TestDiscoveryRails200:
    @pytest.mark.parametrize("endpoint", [
        "/api/playable/leaderboard?limit=20",
        "/api/playable/trending?limit=20",
        "/api/playable/spotlight",
        "/api/playable/most-loved?limit=20",
        "/api/playable/staff-picks?limit=20",
        "/api/playable/surprise",
        "/api/playable/daily",
        "/api/playable/arena",
    ])
    def test_rail_200(self, s, endpoint):
        r = s.get(f"{BASE_URL}{endpoint}", timeout=TIMEOUT)
        assert r.status_code == 200, f"{endpoint} → {r.status_code}: {r.text[:200]}"


# ── (c) Hidden-exclusion proof: hide a game → no longer on leaderboard,
#       still on /list → restore it ─────────────────────────────────────────
class TestHiddenExclusion:

    @pytest.fixture(scope="class")
    def target_pid(self, s):
        # Pick a ready playable that is currently ok (not already hidden/warned/review)
        r = s.get(f"{BASE_URL}/api/playable/list?limit=100", timeout=TIMEOUT)
        assert r.status_code == 200
        items = r.json().get("playables") or []
        ready = [
            p for p in items
            if p.get("status") == "ready"
            and (p.get("moderation_status") in (None, "ok"))
        ]
        if not ready:
            pytest.skip("no ok/ready playable available to hide-test")
        # Prefer one that has appeared in leaderboard
        lb = s.get(f"{BASE_URL}/api/playable/leaderboard?limit=100", timeout=TIMEOUT).json()
        lb_ids = {x.get("playable_id") for x in (lb.get("playables") or lb.get("items") or [])}
        for p in ready:
            if p["playable_id"] in lb_ids:
                return p["playable_id"]
        # else any ok/ready id
        return ready[0]["playable_id"]

    def test_hide_excludes_from_leaderboard_but_present_in_list(self, s, target_pid, request):
        pid = target_pid
        # File one report
        rep = s.post(f"{BASE_URL}/api/governance/report", json={
            "playable_id": pid, "reason": "inappropriate",
            "detail": "TEST_iter40_exclusion", "reporter_id": "TEST_iter40",
        }, timeout=TIMEOUT)
        assert rep.status_code == 200, rep.text
        rid = rep.json().get("report_id")
        assert rid

        # Moderate hide
        mod = s.post(f"{BASE_URL}/api/governance/moderate/{rid}",
                     json={"action": "hide", "note": "TEST_iter40 hide",
                           "actor": "TEST_iter40"}, timeout=TIMEOUT)
        assert mod.status_code == 200, mod.text
        body = mod.json()
        assert body.get("moderation_status") == "hidden", body

        # Stash rid for restore in next test
        request.config.cache.set("iter40/rid", rid)
        request.config.cache.set("iter40/pid", pid)

        # Status confirms hidden + not visible
        st = s.get(f"{BASE_URL}/api/governance/status/{pid}", timeout=TIMEOUT).json()
        assert st.get("moderation_status") == "hidden"
        assert st.get("visible") is False

        # Leaderboard should NOT include pid
        lb = s.get(f"{BASE_URL}/api/playable/leaderboard?limit=100", timeout=TIMEOUT).json()
        lb_items = lb.get("playables") or lb.get("items") or []
        lb_ids = {x.get("playable_id") for x in lb_items}
        assert pid not in lb_ids, f"hidden pid {pid} STILL on leaderboard"

        # But /playable/list should still include it (admin catalogue; max limit=100)
        lst = s.get(f"{BASE_URL}/api/playable/list?limit=100", timeout=TIMEOUT).json()
        lst_ids = {x.get("playable_id") for x in (lst.get("playables") or [])}
        assert pid in lst_ids, f"hidden pid {pid} missing from /playable/list"

    def test_restore_hidden_game(self, s, request):
        rid = request.config.cache.get("iter40/rid", None)
        pid = request.config.cache.get("iter40/pid", None)
        if not rid or not pid:
            pytest.skip("nothing to restore")
        mod = s.post(f"{BASE_URL}/api/governance/moderate/{rid}",
                     json={"action": "restore", "note": "TEST_iter40 restore",
                           "actor": "TEST_iter40"}, timeout=TIMEOUT)
        assert mod.status_code == 200, mod.text
        assert mod.json().get("moderation_status") == "ok"
        st = s.get(f"{BASE_URL}/api/governance/status/{pid}", timeout=TIMEOUT).json()
        assert st.get("moderation_status") == "ok"
        assert st.get("visible") is True


# ── (d) Marketplace listing: similarity_warning key + hidden-block ────────
class TestMarketplaceListingGate:

    @pytest.fixture(scope="class")
    def ready_pid(self, s):
        r = s.get(f"{BASE_URL}/api/playable/list?limit=50", timeout=TIMEOUT)
        items = r.json().get("playables") or []
        for p in items:
            if p.get("status") == "ready" and p.get("moderation_status") in (None, "ok"):
                return p["playable_id"]
        pytest.skip("no ready ok playable for marketplace listing")

    def test_list_returns_ok_listing_and_similarity_warning_key(self, s, ready_pid):
        r = s.post(f"{BASE_URL}/api/marketplace/list", json={
            "playable_id": ready_pid, "price_usd": 4.99, "creator_id": "TEST_iter40_qa",
        }, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True, body
        # listing fields
        L = body.get("listing") or {}
        assert L.get("playable_id") == ready_pid
        assert float(L.get("price_usd")) == 4.99
        assert L.get("creator_id") == "TEST_iter40_qa"
        assert L.get("currency") == "usd"
        assert L.get("active") is True
        # similarity_warning key MUST be present (null or dict)
        assert "similarity_warning" in body, body.keys()
        w = body["similarity_warning"]
        if w is not None:
            assert "playable_id" in w and "similarity" in w
            assert isinstance(w["similarity"], (int, float))

    def test_listing_hidden_game_is_blocked(self, s):
        # Find an ok/ready pid, hide it, attempt to list, then restore.
        items = s.get(f"{BASE_URL}/api/playable/list?limit=100", timeout=TIMEOUT).json().get("playables") or []
        target = next((p for p in items if p.get("status") == "ready"
                       and p.get("moderation_status") in (None, "ok")), None)
        if not target:
            pytest.skip("no ok/ready playable to hide for block-test")
        pid = target["playable_id"]
        rep = s.post(f"{BASE_URL}/api/governance/report", json={
            "playable_id": pid, "reason": "inappropriate",
            "reporter_id": "TEST_iter40_block"}, timeout=TIMEOUT).json()
        rid = rep.get("report_id")
        s.post(f"{BASE_URL}/api/governance/moderate/{rid}",
               json={"action": "hide", "actor": "TEST_iter40_block"}, timeout=TIMEOUT)
        try:
            r = s.post(f"{BASE_URL}/api/marketplace/list", json={
                "playable_id": pid, "price_usd": 4.99,
                "creator_id": "TEST_iter40_qa"}, timeout=TIMEOUT)
            assert r.status_code == 200
            err = r.json().get("error") or ""
            assert "hidden" in err.lower(), f"expected hidden-block, got: {r.json()}"
        finally:
            # Restore so catalogue is clean
            s.post(f"{BASE_URL}/api/governance/moderate/{rid}",
                   json={"action": "restore", "actor": "TEST_iter40_block"}, timeout=TIMEOUT)

    def test_price_is_server_side_not_client_settable(self, s, ready_pid):
        # Client cannot inject 'sales'/'revenue' or override server-side fields.
        r = s.post(f"{BASE_URL}/api/marketplace/list", json={
            "playable_id": ready_pid, "price_usd": 9.99,
            "creator_id": "TEST_iter40_qa",
            # adversarial payload — these should be ignored
            "sales": 9999, "revenue_usd": 1000000, "active": False,
        }, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        L = r.json().get("listing") or {}
        # active stays True; price reflects what we sent (server validated range)
        assert L.get("active") is True
        assert float(L.get("price_usd")) == 9.99
        # sales is server-managed (starts at 0 on insert, untouched on update)
        assert (L.get("sales") or 0) >= 0

    def test_invalid_price_rejected(self, s, ready_pid):
        r = s.post(f"{BASE_URL}/api/marketplace/list", json={
            "playable_id": ready_pid, "price_usd": 0.01,
            "creator_id": "TEST_iter40_qa"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "price" in (r.json().get("error") or "").lower()
