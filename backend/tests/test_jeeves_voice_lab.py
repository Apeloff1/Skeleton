"""Backend tests for Jeeves Voice Lab (Expressive TTS) + AI Reader expressive path.

Endpoints under test:
- GET  /api/jeeves-voice/voice/tones
- GET  /api/jeeves-voice/cast
- POST /api/jeeves-voice/voice/speak
- GET  /api/jeeves-voice/voice/preview
- POST /api/jeeves-voice/narrate
- POST /api/reader/speak (expressive + default)
"""
import os
import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")

TIMEOUT = 60  # TTS can take ~3-10s


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------- catalog endpoints ----------------

class TestVoiceCatalog:
    def test_tones_returns_12(self, client):
        r = client.get(f"{BASE_URL}/api/jeeves-voice/voice/tones", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "tones" in j and isinstance(j["tones"], list)
        assert len(j["tones"]) == 12, f"expected 12 tones, got {len(j['tones'])}"
        # Each tone has required fields
        ids = set()
        for t in j["tones"]:
            assert {"id", "label", "voice", "speed"}.issubset(t.keys()), t
            ids.add(t["id"])
        # Spot-check key tones
        for required in ["butler", "storyteller", "dramatic", "narrator", "gentle", "calm"]:
            assert required in ids, f"missing tone {required}"
        assert j.get("default") == "butler"

    def test_cast_returns_11_agents(self, client):
        r = client.get(f"{BASE_URL}/api/jeeves-voice/cast", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "cast" in j and isinstance(j["cast"], list)
        assert len(j["cast"]) == 11, f"expected 11 agents, got {len(j['cast'])}"
        agents = {c["agent"] for c in j["cast"]}
        for needed in ["Jeeves", "Orchestrator", "WorldForgeAgent", "NarrativeQuestAgent", "BuildAgent"]:
            assert needed in agents, f"missing agent {needed}"
        # each cast entry has fields
        for c in j["cast"]:
            assert {"agent", "title", "tone", "tone_label", "voice", "speed"}.issubset(c.keys()), c


# ---------------- /voice/speak tone tests ----------------

@pytest.mark.parametrize("tone", ["butler", "storyteller", "dramatic"])
class TestVoiceSpeakTones:
    def test_speak_real_audio(self, client, tone):
        body = {"text": "Hello - welcome to the world we will build together.", "tone": tone}
        r = client.post(f"{BASE_URL}/api/jeeves-voice/voice/speak", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("status") == "success", f"expected success, got {j}"
        b64 = j.get("audio_base64") or ""
        assert isinstance(b64, str) and len(b64) > 5000, (
            f"audio_base64 too small ({len(b64)}) - likely fallback for tone={tone}"
        )
        assert j.get("tone") == tone
        # Cadence shaping: hyphen converted to em-dash
        assert "—" in (j.get("spoken_text") or ""), f"cadence em-dash missing for tone={tone}"


class TestEmotionalStateMapping:
    def test_frustrated_maps_to_gentle(self, client):
        body = {"text": "Take a breath. We will solve this together.",
                "tone": "auto", "emotional_state": "frustrated"}
        r = client.post(f"{BASE_URL}/api/jeeves-voice/voice/speak", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("status") == "success", j
        # frustrated → gentle per EMOTION_TONE map
        assert j.get("tone") == "gentle", f"expected gentle, got {j.get('tone')}"
        assert len(j.get("audio_base64") or "") > 5000


# ---------------- /voice/preview ----------------

class TestVoicePreview:
    def test_preview_storyteller(self, client):
        r = client.get(f"{BASE_URL}/api/jeeves-voice/voice/preview?tone=storyteller", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("status") == "success", j
        assert len(j.get("audio_base64") or "") > 5000
        assert isinstance(j.get("sample_text"), str) and len(j["sample_text"]) > 10
        assert j.get("tone") == "storyteller"


# ---------------- /narrate ----------------

class TestNarrate:
    def test_narrate_multi_chunk(self, client):
        # ~200 chars so with max_chars=80 should produce >1 chunks
        text = ("In the age before memory, the first star was forged. "
                "From its light all the worlds were born. "
                "And then the hero arose, against the long dark, to carry the lantern home.")
        body = {"text": text, "tone": "narrator", "max_chars": 80}
        r = client.post(f"{BASE_URL}/api/jeeves-voice/narrate", json=body, timeout=TIMEOUT * 3)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("chunks", 0) > 1, f"expected >1 chunks, got {j.get('chunks')}"
        clips = j.get("clips") or []
        assert len(clips) == j["chunks"]
        # Every clip should be success (real audio)
        for c in clips:
            assert c.get("status") == "success", f"clip {c.get('index')} not success: {c}"
            assert len(c.get("audio_base64") or "") > 1000


# ---------------- /api/reader/speak ----------------

class TestReaderSpeak:
    def test_reader_expressive_with_tone(self, client):
        # POST with query params (FastAPI Query param)
        r = client.post(
            f"{BASE_URL}/api/reader/speak",
            params={"text": "Welcome back - lovely to see you again.", "tone": "warm"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("status") == "success", j
        assert len(j.get("audio_base64") or "") > 5000
        assert j.get("tone") == "warm"

    def test_reader_default_no_tone(self, client):
        r = client.post(
            f"{BASE_URL}/api/reader/speak",
            params={"text": "hello"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j.get("audio_base64") or "") > 1000


# ---------------- error handling ----------------

class TestErrorHandling:
    def test_speak_empty_text_400(self, client):
        r = client.post(f"{BASE_URL}/api/jeeves-voice/voice/speak", json={"text": "", "tone": "butler"}, timeout=TIMEOUT)
        assert r.status_code == 400

    def test_narrate_empty_text_400(self, client):
        r = client.post(f"{BASE_URL}/api/jeeves-voice/narrate", json={"text": "", "tone": "narrator"}, timeout=TIMEOUT)
        assert r.status_code == 400
