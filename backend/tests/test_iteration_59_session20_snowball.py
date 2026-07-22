"""
Session 20 — ☃️ Snowball Build backend tests.

Covers GET /api/snowball/{pid} shape + gating + growing GDD + lock/unlock reuse of
the existing pipeline approve endpoint. No new endpoints introduced — snowball is a
read-only ladder built from the KB; run/refine/lock reuse the existing forge endpoints.
"""
from __future__ import annotations

import os
import requests
import pytest

def _load_base_url():
    u = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
    if not u:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                        u = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except FileNotFoundError:
            pass
    assert u, "EXPO_PUBLIC_BACKEND_URL must be set"
    return u.rstrip("/")


BASE_URL = _load_base_url()

RICH_PID = "d02790d6d8174ff59bf7005221cd7609"   # most stages built, next should be 'qa'
FRESH_PID = "86f6be7bf0c94a48b43be198bd840236"  # no KB artifacts, next should be 'spec'

EXPECTED_LADDER_KEYS = [
    "spec", "world", "narrative", "mechanics",
    "procedural", "assets", "qa", "build", "launch",
]


# ──────────────────────────── module: snowball — shape ───────────────────────────
class TestSnowballShape:
    """GET /api/snowball/{pid} returns the ordered ladder + meter + growing GDD."""

    def test_rich_game_top_level_shape(self):
        r = requests.get(f"{BASE_URL}/api/snowball/{RICH_PID}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("game_id", "title", "mode", "steps", "built", "locked",
                  "total", "percent", "next", "next_label", "gdd",
                  "gdd_chars", "size_label"):
            assert k in d, f"missing key {k!r}"
        assert d["game_id"] == RICH_PID
        assert d["total"] == 9
        assert isinstance(d["steps"], list) and len(d["steps"]) == 10  # mode + 9
        assert isinstance(d["gdd"], str)
        assert d["gdd_chars"] == len(d["gdd"])

    def test_step0_is_mode_and_locked(self):
        d = requests.get(f"{BASE_URL}/api/snowball/{RICH_PID}", timeout=15).json()
        s0 = d["steps"][0]
        assert s0["key"] == "mode"
        assert s0["done"] is True
        assert s0["locked"] is True
        assert s0["forge"] is None
        assert s0["is_next"] is False

    def test_ladder_keys_and_per_step_fields(self):
        d = requests.get(f"{BASE_URL}/api/snowball/{RICH_PID}", timeout=15).json()
        keys = [s["key"] for s in d["steps"][1:]]
        assert keys == EXPECTED_LADDER_KEYS
        for s in d["steps"][1:]:
            for f in ("key", "label", "icon", "forge", "done", "locked", "is_next", "summary"):
                assert f in s, f"step {s.get('key')} missing {f}"
            assert s["forge"] == s["key"]

    def test_exactly_one_is_next_and_it_is_first_unbuilt(self):
        d = requests.get(f"{BASE_URL}/api/snowball/{RICH_PID}", timeout=15).json()
        is_nexts = [s for s in d["steps"] if s.get("is_next")]
        assert len(is_nexts) == 1
        nxt = is_nexts[0]
        # first not-done step (skipping mode)
        first_unbuilt = next(s for s in d["steps"][1:] if not s["done"])
        assert nxt["key"] == first_unbuilt["key"]
        assert d["next"] == nxt["key"]
        assert d["next_label"] == nxt["label"]

    def test_rich_game_next_is_qa(self):
        d = requests.get(f"{BASE_URL}/api/snowball/{RICH_PID}", timeout=15).json()
        assert d["next"] == "qa", f"expected next='qa', got {d['next']}"


# ──────────────────────────── module: snowball — gating ──────────────────────────
class TestSnowballGating:
    """Fresh game (no KB) → next=spec; only spec is_next; gdd minimal."""

    def test_fresh_game_next_is_spec_only(self):
        d = requests.get(f"{BASE_URL}/api/snowball/{FRESH_PID}", timeout=15).json()
        assert d["next"] == "spec"
        assert d["built"] == 0
        spec = next(s for s in d["steps"] if s["key"] == "spec")
        assert spec["is_next"] is True
        for s in d["steps"]:
            if s["key"] != "spec":
                assert s["is_next"] is False, f"{s['key']} should not be is_next"

    def test_growing_gdd_smaller_on_fresh(self):
        rich = requests.get(f"{BASE_URL}/api/snowball/{RICH_PID}", timeout=15).json()
        fresh = requests.get(f"{BASE_URL}/api/snowball/{FRESH_PID}", timeout=15).json()
        assert fresh["gdd_chars"] < rich["gdd_chars"]
        # fresh game has NO core_specs section
        assert "## 1. Concept & Core Specs" not in fresh["gdd"]
        assert "# 🎮 Game Design Document" in fresh["gdd"]

    def test_rich_gdd_has_built_sections(self):
        d = requests.get(f"{BASE_URL}/api/snowball/{RICH_PID}", timeout=15).json()
        gdd = d["gdd"]
        assert "# 🎮 Game Design Document" in gdd
        # all artifacts built on RICH_PID except qa → spec/world/narrative/mech/proc/assets/build/launch
        for header in [
            "## 1. Concept & Core Specs",
            "## 2. World & Lore",
            "## 3. Narrative & Quests",
            "## 4. Mechanics & Systems",
            "## 5. Procedural Generation",
            "## 6. Assets",
            "## 8. Build & Package",
            "## 9. Launch Prep",
        ]:
            assert header in gdd, f"missing section {header!r}"
        # qa not built → no section 7
        assert "## 7. Playtest & QA" not in gdd


# ──────────────────────────── module: snowball — errors ──────────────────────────
class TestSnowballMissingGame:
    def test_unknown_id_returns_error(self):
        r = requests.get(f"{BASE_URL}/api/snowball/bogus", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"error": "game not found"}


# ──────────────────────── module: lock / unlock reuse approve ────────────────────
class TestSnowballLockReuse:
    """Snowball does NOT introduce new endpoints — lock/unlock reuse approve.
    We toggle 'spec' approval and verify it round-trips through GET /api/snowball.
    """

    PID = RICH_PID

    @pytest.fixture(autouse=True)
    def _reset(self):
        # ensure initial state is unlocked
        requests.post(f"{BASE_URL}/api/pipeline/{self.PID}/approve/spec",
                      json={"approved": False}, timeout=15)
        yield
        # final cleanup: unlock again
        requests.post(f"{BASE_URL}/api/pipeline/{self.PID}/approve/spec",
                      json={"approved": False}, timeout=15)

    def test_lock_then_unlock_round_trip(self):
        before = requests.get(f"{BASE_URL}/api/snowball/{self.PID}", timeout=15).json()
        spec_before = next(s for s in before["steps"] if s["key"] == "spec")
        assert spec_before["locked"] is False
        locked_before = before["locked"]

        # LOCK via existing approve endpoint
        ra = requests.post(f"{BASE_URL}/api/pipeline/{self.PID}/approve/spec",
                           json={"approved": True}, timeout=15)
        assert ra.status_code == 200
        assert ra.json().get("ok") is True

        mid = requests.get(f"{BASE_URL}/api/snowball/{self.PID}", timeout=15).json()
        spec_mid = next(s for s in mid["steps"] if s["key"] == "spec")
        assert spec_mid["locked"] is True
        assert mid["locked"] == locked_before + 1

        # UNLOCK
        ru = requests.post(f"{BASE_URL}/api/pipeline/{self.PID}/approve/spec",
                           json={"approved": False}, timeout=15)
        assert ru.status_code == 200

        after = requests.get(f"{BASE_URL}/api/snowball/{self.PID}", timeout=15).json()
        spec_after = next(s for s in after["steps"] if s["key"] == "spec")
        assert spec_after["locked"] is False
        assert after["locked"] == locked_before
