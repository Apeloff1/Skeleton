"""
Iteration 17 / Session 6 — Live-Ops 'Theme of the Week' rail + Discover deltas.

Backend slice:
  • GET /api/playable/theme-of-week?limit=12 → {theme, prompt, week, games[], count}
    - games is allowed to be empty (valid live-ops state) for the current week.
    - When present, each game row has playable_id/title/genre/overall/has_cover.

Frontend slice (covered separately via Playwright); here we only smoke-check
that the other discover-feed endpoints used by /discover render OK.
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
           os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to local file scrape so tests don't false-fail in CI
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL"):
                BASE_URL = line.strip().split("=", 1)[1].strip().rstrip("/")
                break

TIMEOUT = 20


# ── theme-of-week endpoint ────────────────────────────────────────────────────
class TestThemeOfWeek:
    def test_endpoint_200_and_shape(self):
        r = requests.get(f"{BASE_URL}/api/playable/theme-of-week?limit=12", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        body = r.json()
        # Required keys
        for k in ("theme", "prompt", "week", "games", "count"):
            assert k in body, f"missing key: {k}"
        assert isinstance(body["theme"], str) and body["theme"], "theme must be non-empty string"
        assert isinstance(body["prompt"], str) and body["prompt"], "prompt must be non-empty string"
        assert isinstance(body["week"], int), "week must be int"
        assert isinstance(body["games"], list), "games must be list"
        assert isinstance(body["count"], int), "count must be int"
        # count must equal len(games)
        assert body["count"] == len(body["games"]), \
            f"count {body['count']} != len(games) {len(body['games'])}"

    def test_game_rows_shape_when_present(self):
        r = requests.get(f"{BASE_URL}/api/playable/theme-of-week?limit=12", timeout=TIMEOUT)
        body = r.json()
        # Empty array is VALID this week — skip row checks if so.
        if not body["games"]:
            pytest.skip("Theme rail is empty this week (valid live-ops state).")
        for g in body["games"]:
            for k in ("playable_id", "title", "genre", "overall", "has_cover"):
                assert k in g, f"row missing key: {k}"

    def test_limit_param_respected(self):
        # tiny limit ⇒ at most that many rows
        r = requests.get(f"{BASE_URL}/api/playable/theme-of-week?limit=3", timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert len(body["games"]) <= 3
        assert body["count"] == len(body["games"])

    def test_prompt_mentions_theme(self):
        r = requests.get(f"{BASE_URL}/api/playable/theme-of-week?limit=12", timeout=TIMEOUT)
        body = r.json()
        # Prompt should reference the active theme so the Daily-style banner makes sense.
        assert body["theme"].lower() in body["prompt"].lower(), \
            f"prompt does not reference theme: {body!r}"


# ── adjacent rails used by /discover (smoke) ─────────────────────────────────
class TestDiscoverFeedDependencies:
    @pytest.mark.parametrize("path,key", [
        ("/api/playable/spotlight", "spotlight"),
        ("/api/playable/daily", "theme"),
        ("/api/playable/trending?limit=12&hours=24", "trending"),
        ("/api/playable/staff-picks?limit=12", "staff_picks"),
        ("/api/playable/most-loved?limit=12", "most_loved"),
    ])
    def test_feed_endpoints_ok(self, path, key):
        r = requests.get(f"{BASE_URL}{path}", timeout=TIMEOUT)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert key in body, f"{path} missing key {key}"
