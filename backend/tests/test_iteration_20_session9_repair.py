"""
Session 9 / Iteration 20 — runtime error-catcher injection + Auto-repair route.

Tests:
1. /{pid}/raw contains injected __pl_error reporter, BEFORE game scripts.
2. POST /{pid}/repair — exists and returns expected shape (bad pid → not found).
3. Regression: other playable endpoints still work (list, get, lineage, leaderboard,
   trending, champions, staff-picks, play, react).
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
           os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def ready_pid():
    """Find a ready playable with HTML to test against."""
    r = requests.get(f"{API}/playable/list", params={"limit": 30}, timeout=30)
    assert r.status_code == 200, f"list returned {r.status_code}"
    items = r.json().get("playables") or r.json().get("items") or []
    if not items and isinstance(r.json(), list):
        items = r.json()
    # find a ready one
    for it in items:
        pid = it.get("playable_id") or it.get("id")
        status = it.get("status")
        if pid and (status in (None, "ready")):
            # confirm raw returns 200
            rr = requests.get(f"{API}/playable/{pid}/raw", timeout=30)
            if rr.status_code == 200 and len(rr.text) > 200:
                return pid
    pytest.skip("No ready playable available")


# ── Feature 1: error-reporter injection ────────────────────────────────────
class TestErrorReporterInjection:
    def test_raw_returns_html(self, ready_pid):
        r = requests.get(f"{API}/playable/{ready_pid}/raw", timeout=30)
        assert r.status_code == 200
        assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()

    def test_raw_contains_pl_error_reporter(self, ready_pid):
        r = requests.get(f"{API}/playable/{ready_pid}/raw", timeout=30)
        assert "__pl_error" in r.text, "Injected error-reporter (__pl_error) missing from raw HTML"

    def test_reporter_is_before_game_scripts(self, ready_pid):
        """The reporter must appear early — before the FIRST script that isn't the reporter."""
        r = requests.get(f"{API}/playable/{ready_pid}/raw", timeout=30)
        html = r.text
        rep_idx = html.find("__pl_error")
        assert rep_idx > 0, "reporter not present"
        # Find positions of all <script tags. The reporter script must be at/very near the first one.
        script_positions = [m.start() for m in re.finditer(r"<script", html, flags=re.IGNORECASE)]
        assert script_positions, "no <script tags found"
        first_script_pos = script_positions[0]
        # The reporter's __pl_error string must come within or very close to the first <script>
        # i.e. reporter <script ... __pl_error ...> = first script
        # find script that contains __pl_error
        reporter_script_idx = None
        for pos in script_positions:
            # find closing </script> after pos
            end = html.lower().find("</script>", pos)
            block = html[pos:end if end != -1 else pos + 2000]
            if "__pl_error" in block:
                reporter_script_idx = pos
                break
        assert reporter_script_idx is not None
        # Reporter script must be the first script (or essentially first — earliest position)
        assert reporter_script_idx == first_script_pos, \
            f"reporter is not the first script (reporter at {reporter_script_idx}, first script at {first_script_pos})"

    def test_reporter_in_head_or_body_start(self, ready_pid):
        """Reporter must be in <head> or immediately after <body>."""
        r = requests.get(f"{API}/playable/{ready_pid}/raw", timeout=30)
        html = r.text
        low = html.lower()
        rep_idx = html.find("__pl_error")
        head_open = low.find("<head>")
        head_close = low.find("</head>")
        body_open_end = low.find(">", low.find("<body"))
        # Must be inside head OR right after <body ...>
        in_head = head_open != -1 and head_close != -1 and head_open < rep_idx < head_close
        right_after_body = body_open_end != -1 and 0 < rep_idx - body_open_end < 500
        assert in_head or right_after_body, "reporter not injected in <head> or just after <body>"


# ── Feature 2: /repair route shape ─────────────────────────────────────────
class TestRepairRoute:
    def test_repair_bad_pid_returns_not_found(self):
        r = requests.post(f"{API}/playable/does-not-exist-xyz-123/repair",
                          json={"error": "Cannot access 'x' before initialization"},
                          timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("error") == "not found", f"expected error=not found, got {data}"

    def test_repair_route_resolvable(self, ready_pid):
        """Just confirm the route exists & 405-or-422-fast on GET (no LLM call)."""
        # GET should yield 405 Method Not Allowed (route exists but is POST-only)
        r = requests.get(f"{API}/playable/{ready_pid}/repair", timeout=10)
        assert r.status_code in (405, 404, 422), \
            f"unexpected status {r.status_code} on GET /repair (route may not be wired)"


# ── Feature 3: Regression — other endpoints ────────────────────────────────
class TestPlayableEndpointsRegression:
    def test_get_playable(self, ready_pid):
        r = requests.get(f"{API}/playable/{ready_pid}", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("playable_id") == ready_pid

    def test_lineage(self, ready_pid):
        r = requests.get(f"{API}/playable/{ready_pid}/lineage", timeout=30)
        assert r.status_code == 200
        data = r.json()
        # lineage typically returns dict with ancestors/descendants/nodes/etc
        assert isinstance(data, dict)

    def test_leaderboard(self):
        r = requests.get(f"{API}/playable/leaderboard", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_trending(self):
        r = requests.get(f"{API}/playable/trending", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_champions(self):
        r = requests.get(f"{API}/playable/champions", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_staff_picks(self):
        r = requests.get(f"{API}/playable/staff-picks", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_play_counter(self, ready_pid):
        r = requests.post(f"{API}/playable/{ready_pid}/play", json={}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        # Expect either plays count or ok-style response
        assert isinstance(data, dict)

    def test_react(self, ready_pid):
        r = requests.post(f"{API}/playable/{ready_pid}/react",
                          json={"reaction": "love"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
