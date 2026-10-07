"""
Iteration 58 / Session 19 — Mode Selection (Stage 1) backend tests.

Covers:
- GET /api/modes/options → 12 modes payload (shape & ids)
- POST /api/modes/forge-brief → inheritance brief with characters/quests/factions for sequel,
                                invalid mode guard, missing-parent guard.
- (slow, gated by RUN_LLM=1) full async generate threading: forged_from + derive_mode survive
  on the new playable, and the pipeline Mode stage detail reflects the chosen mode.
"""
import os
import time
import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "https://gemini-game-craft.preview.emergentagent.com"
).rstrip("/")

PARENT_ID = "d02790d6d8174ff59bf7005221cd7609"

EXPECTED_MODE_IDS = {
    "sequel", "prequel", "expansion", "series_variant", "conclusion",
    "remaster", "spinoff", "crossover", "reboot", "dlc_pack", "demake", "what_if",
}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- modes options -----------------------------------------------------------
class TestModesOptions:
    def test_options_returns_12_modes(self, api):
        r = api.get(f"{BASE_URL}/api/modes/options", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("count") == 12, body
        modes = body.get("modes")
        assert isinstance(modes, list) and len(modes) == 12
        ids = {m["id"] for m in modes}
        assert ids == EXPECTED_MODE_IDS, ids
        # shape: each mode has id/label/emoji/inherit/directive
        for m in modes:
            for k in ("id", "label", "emoji", "inherit", "directive"):
                assert k in m and m[k], f"mode {m.get('id')} missing {k}"


# --- forge-brief inheritance & guards ---------------------------------------
class TestForgeBrief:
    def test_sequel_inherits_canon(self, api):
        r = api.post(
            f"{BASE_URL}/api/modes/forge-brief",
            json={"parent_id": PARENT_ID, "mode": "sequel", "extra": ""},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "error" not in body, body
        assert body.get("mode") == "sequel"
        assert isinstance(body.get("title"), str) and len(body["title"]) > 0
        assert isinstance(body.get("brief"), str) and len(body["brief"]) > 50
        inh = body.get("inherited") or {}
        # sequel inherits world+characters+mechanics → expect characters; with KB game,
        # quests + factions should also be populated.
        assert inh.get("contract", "").startswith("world+characters")
        assert "characters" in inh and isinstance(inh["characters"], list) and len(inh["characters"]) > 0, inh
        assert "quests" in inh and isinstance(inh["quests"], list) and len(inh["quests"]) > 0, inh
        assert "factions" in inh and isinstance(inh["factions"], list) and len(inh["factions"]) > 0, inh
        brief = body["brief"]
        assert "RETURNING/CANON CHARACTERS" in brief, brief[:500]
        assert "CANON STORY BEATS" in brief, brief[:500]
        assert "CANON FACTIONS" in brief, brief[:500]
        assert "INHERITANCE CONTRACT" in brief

    def test_extra_note_threaded(self, api):
        r = api.post(
            f"{BASE_URL}/api/modes/forge-brief",
            json={"parent_id": PARENT_ID, "mode": "expansion", "extra": "set it on a frozen moon"},
            timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        assert "CREATOR NOTE: set it on a frozen moon" in body.get("brief", "")

    def test_reboot_only_inherits_theme(self, api):
        r = api.post(
            f"{BASE_URL}/api/modes/forge-brief",
            json={"parent_id": PARENT_ID, "mode": "reboot", "extra": ""},
            timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        inh = body.get("inherited") or {}
        # reboot's contract is "theme" — should not pull characters/quests/factions
        assert inh.get("contract") == "theme"
        assert "characters" not in inh
        assert "quests" not in inh
        assert "factions" not in inh
        # title for reboot uses special suffix
        assert "Reboot" in body.get("title", "")

    def test_unknown_mode_guard(self, api):
        r = api.post(
            f"{BASE_URL}/api/modes/forge-brief",
            json={"parent_id": PARENT_ID, "mode": "frobnicate", "extra": ""},
            timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("error") == "unknown mode"
        valid = body.get("valid") or []
        assert set(valid) == EXPECTED_MODE_IDS

    def test_missing_parent_guard(self, api):
        r = api.post(
            f"{BASE_URL}/api/modes/forge-brief",
            json={"parent_id": "nonexistent_parent_xyz_12345", "mode": "sequel"},
            timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("error") == "parent game not found"


# --- async generate threading (slow) ----------------------------------------
@pytest.mark.skipif(os.environ.get("RUN_LLM") != "1", reason="LLM gen ~60-180s; set RUN_LLM=1 to enable")
class TestModeThreadedGenerate:
    def test_sequel_generate_threads_mode_and_lineage(self, api):
        # 1) forge brief
        fb = api.post(
            f"{BASE_URL}/api/modes/forge-brief",
            json={"parent_id": PARENT_ID, "mode": "sequel"},
            timeout=30,
        ).json()
        assert "brief" in fb and "title" in fb

        # 2) kick async generate with derive_mode + forged_from
        kick = api.post(
            f"{BASE_URL}/api/playable/generate/async",
            json={
                "brief": fb["brief"],
                "title": fb["title"],
                "depth": "fast",
                "forged_from": PARENT_ID,
                "derive_mode": "sequel",
            },
            timeout=30,
        )
        assert kick.status_code == 200, kick.text
        kdata = kick.json()
        job_id = kdata.get("job_id")
        assert job_id, kdata

        # 3) poll up to ~3 min
        new_id = None
        deadline = time.time() + 200
        last = {}
        while time.time() < deadline:
            jr = api.get(f"{BASE_URL}/api/playable/job/{job_id}", timeout=20).json()
            last = jr
            st = jr.get("job_status")
            if st == "done":
                new_id = jr.get("playable_id") or jr.get("id")
                break
            if st == "error":
                pytest.fail(f"generation errored: {jr}")
            time.sleep(4)
        assert new_id, f"job did not finish in time; last={last}"

        # 4) new playable carries forged_from + derive_mode
        pl = api.get(f"{BASE_URL}/api/playable/{new_id}", timeout=20).json()
        assert pl.get("forged_from") == PARENT_ID, pl
        assert pl.get("derive_mode") == "sequel", pl

        # 5) pipeline Mode stage detail reflects sequel
        pp = api.get(f"{BASE_URL}/api/playable/{new_id}/pipeline", timeout=20).json()
        stages = pp.get("stages") or []
        mode_stage = next((s for s in stages if s.get("id") == "mode" or "mode" in str(s.get("key", "")).lower()), None)
        # Fallback: search any stage whose detail/text mentions sequel
        blob = str(pp).lower()
        assert "sequel" in blob, f"pipeline payload did not mention sequel: {pp}"
        # If a dedicated mode stage exists, sanity-check its detail
        if mode_stage:
            assert "sequel" in str(mode_stage).lower()
