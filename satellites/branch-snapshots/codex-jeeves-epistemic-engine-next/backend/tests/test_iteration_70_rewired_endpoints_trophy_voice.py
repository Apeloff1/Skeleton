"""
Iteration 70 — Rewired write-only collections + Trophy Case cinematic voice.

Tests:
  • GET /api/telemetry/critical/recent     — rewired (was 404 due to double /api prefix)
  • GET /api/hub/expansions/installed       — rewired (was 404 due to double /api prefix)
  • GET /api/tournaments/rewards/ledger     — Trophy Case data source
  • POST /api/jeeves-voice/voice/speak      — HD TTS, tone=triumphant, audio_base64 present
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
if not BASE_URL:
    # Fallback to local for in-container testing
    BASE_URL = "http://localhost:8001"
BASE_URL = BASE_URL.rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Rewired endpoints (the focus of this iteration) ──────────────────────────
class TestRewiredEndpoints:
    def test_telemetry_critical_recent(self, api):
        r = api.get(f"{BASE_URL}/api/telemetry/critical/recent", timeout=20)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
        j = r.json()
        assert isinstance(j, dict)
        assert "events" in j and isinstance(j["events"], list)
        assert "count" in j and isinstance(j["count"], int)
        assert j["count"] == len(j["events"])

    def test_hub_expansions_installed(self, api):
        r = api.get(f"{BASE_URL}/api/hub/expansions/installed", timeout=20)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
        j = r.json()
        assert isinstance(j, dict)
        assert "expansions" in j and isinstance(j["expansions"], list)
        assert "count" in j and isinstance(j["count"], int)
        assert j["count"] == len(j["expansions"])


# ── Trophy Case data source ──────────────────────────────────────────────────
class TestTournamentRewardsLedger:
    def test_rewards_ledger_200(self, api):
        r = api.get(f"{BASE_URL}/api/tournaments/rewards/ledger", timeout=30)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
        j = r.json()
        assert isinstance(j, dict)
        assert "rewards" in j and isinstance(j["rewards"], list)


# ── HD TTS — triumphant tone for Trophy Case champion-crowned line ───────────
class TestJeevesVoiceSpeak:
    def test_voice_speak_triumphant(self, api):
        payload = {
            "text": "A champion is crowned! The trophy is yours, and the legend is sealed.",
            "tone": "triumphant",
        }
        r = api.post(
            f"{BASE_URL}/api/jeeves-voice/voice/speak",
            json=payload,
            timeout=60,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
        j = r.json()
        assert isinstance(j, dict)
        # If TTS provider key missing → backend returns fallback_text_only.
        if j.get("status") != "success":
            pytest.fail(f"voice/speak returned non-success: {j}")
        assert j.get("audio_base64"), "audio_base64 must be non-empty"
        assert isinstance(j["audio_base64"], str)
        assert len(j["audio_base64"]) > 1000, f"audio_base64 too short ({len(j['audio_base64'])})"
        # Sanity on tone propagation
        assert "tone" in j
