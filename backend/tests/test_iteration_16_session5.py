"""Session-5 deltas: reactions → trending velocity / ranking, /most-loved rail,
reactions_total in leaderboard."""
import os
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE:
    # fallback to frontend public URL key
    BASE = "https://gemini-game-craft.preview.emergentagent.com"
API = f"{BASE}/api"


def _get_ready_pid() -> str:
    r = requests.get(f"{API}/playable/list?limit=10", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data.get("playables") or data.get("items") or data.get("list") or []
    assert items, f"no playables in list response: {data}"
    pid = items[0].get("playable_id") or items[0].get("id")
    assert pid, f"no playable_id in first item: {items[0]}"
    return pid


# ── reactions feed Trending velocity ─────────────────────────────────────────
class TestReactionInTrending:
    def test_react_increments_reacts_window_and_velocity(self):
        pid = _get_ready_pid()
        # 3 reactions on this pid
        for _ in range(3):
            rr = requests.post(f"{API}/playable/{pid}/react", json={"emoji": "🔥"}, timeout=15)
            assert rr.status_code == 200, rr.text
            j = rr.json()
            assert "error" not in j, j

        # fetch trending — pid should be present, reacts_window present and >= 3
        tr = requests.get(f"{API}/playable/trending?hours=24", timeout=15)
        assert tr.status_code == 200, tr.text
        data = tr.json()
        assert "trending" in data and isinstance(data["trending"], list)
        # every row must have reacts_window int
        for row in data["trending"]:
            assert "reacts_window" in row, f"missing reacts_window: {row}"
            assert isinstance(row["reacts_window"], int)
            # velocity formula: plays + votes*2 + reacts
            expected_vel = (row.get("plays_window") or 0) + (row.get("votes_window") or 0) * 2 + (row.get("reacts_window") or 0)
            assert row["velocity"] == expected_vel, f"velocity mismatch row={row}"
        ours = [r for r in data["trending"] if r["playable_id"] == pid]
        assert ours, f"reacted pid {pid} not in trending: {[r['playable_id'] for r in data['trending']]}"
        assert ours[0]["reacts_window"] >= 3


# ── /most-loved ──────────────────────────────────────────────────────────────
class TestMostLoved:
    def test_most_loved_shape_and_filtering(self):
        pid = _get_ready_pid()
        # ensure at least one reaction exists
        rr = requests.post(f"{API}/playable/{pid}/react", json={"emoji": "❤️"}, timeout=15)
        assert rr.status_code == 200, rr.text

        r = requests.get(f"{API}/playable/most-loved?limit=12", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "most_loved" in data and isinstance(data["most_loved"], list)
        assert "count" in data and data["count"] == len(data["most_loved"])
        assert data["count"] >= 1, "expected at least one loved game after seeding"

        totals = []
        for row in data["most_loved"]:
            for fld in ("reactions_total", "title", "genre", "overall", "has_cover"):
                assert fld in row, f"missing {fld} in {row}"
            assert isinstance(row["reactions_total"], int)
            assert row["reactions_total"] > 0, "rail must exclude games with 0 reactions"
            totals.append(row["reactions_total"])
        # descending order
        assert totals == sorted(totals, reverse=True), f"not sorted desc: {totals}"

    def test_limit_param_respected(self):
        r = requests.get(f"{API}/playable/most-loved?limit=3", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert len(data["most_loved"]) <= 3


# ── /leaderboard now exposes reactions_total ─────────────────────────────────
class TestLeaderboardReactionsTotal:
    def test_leaderboard_rows_include_reactions_total(self):
        r = requests.get(f"{API}/playable/leaderboard?limit=5", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "leaderboard" in data and isinstance(data["leaderboard"], list)
        assert len(data["leaderboard"]) > 0, "leaderboard empty"
        for row in data["leaderboard"]:
            assert "reactions_total" in row, f"missing reactions_total in {row}"
            assert isinstance(row["reactions_total"], int)
            assert row["reactions_total"] >= 0

    def test_leaderboard_well_formed_with_loved_boost(self):
        # Loved boost is internal — ensure the route still returns a sorted, valid list.
        r = requests.get(f"{API}/playable/leaderboard?limit=10&sort=score", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        ranks = [row["rank"] for row in data["leaderboard"]]
        assert ranks == list(range(1, len(ranks) + 1)), f"ranks not 1..N: {ranks}"
        scores = [row["score"] for row in data["leaderboard"]]
        assert scores == sorted(scores, reverse=True), f"scores not sorted desc: {scores}"
