"""
Iteration 71 — Verify rewired endpoints now return REAL assets (not simulated stubs):
- /api/imagine/generate (Gemini Nano Banana)
- /api/imagine/cover
- /api/reader/speak (tts-1-hd via Emergent universal key)
- /api/jeeves/speak
- /api/jeeves-voice/trailer
Plus regression: telemetry/critical/recent, hub/expansions/installed, tournaments/rewards/ledger
"""
import os
import base64
import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "https://gemini-game-craft.preview.emergentagent.com"
).rstrip("/")

# Image generation can take up to ~30s
LONG_TIMEOUT = 90
SHORT_TIMEOUT = 30


def _truncate(b64: str, n: int = 12) -> str:
    if not b64:
        return ""
    return b64[:n] + "...(len=" + str(len(b64)) + ")"


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ------- Regression: previously fixed endpoints -------
class TestRegression:
    def test_telemetry_critical_recent(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/telemetry/critical/recent", timeout=SHORT_TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "events" in data and "count" in data

    def test_hub_expansions_installed(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/hub/expansions/installed", timeout=SHORT_TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "expansions" in data and "count" in data

    def test_tournaments_rewards_ledger(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/tournaments/rewards/ledger", timeout=SHORT_TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "rewards" in data


# ------- Image generation (Gemini Nano Banana) -------
class TestImagineGenerate:
    def test_generate_gemini_real_image(self, api_client):
        payload = {
            "prompt": "A vibrant neon cyberpunk city skyline at night, isometric game art",
            "provider": "gemini",
        }
        r = api_client.post(
            f"{BASE_URL}/api/imagine/generate", json=payload, timeout=LONG_TIMEOUT
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:500]}"
        data = r.json()
        assert data.get("status") == "success", f"status not success: {data}"
        images = data.get("images") or []
        assert len(images) > 0, "no images returned"
        b64 = images[0].get("data") or images[0].get("base64") or ""
        print(f"[imagine/generate gemini] image preview: {_truncate(b64)}")
        # Mock 1x1 PNG is ~100 chars; real image should be many KB
        assert len(b64) > 5000, f"image too small (likely mock stub): len={len(b64)}"
        # Should decode as valid base64
        raw = base64.b64decode(b64, validate=False)
        assert len(raw) > 3000, f"decoded image too small: {len(raw)} bytes"

    def test_generate_auto_provider(self, api_client):
        payload = {
            "prompt": "A medieval fantasy castle, painterly key art",
            "provider": "auto",
        }
        r = api_client.post(
            f"{BASE_URL}/api/imagine/generate", json=payload, timeout=LONG_TIMEOUT
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:500]}"
        data = r.json()
        assert data.get("status") == "success", f"status not success: {data}"
        images = data.get("images") or []
        assert len(images) > 0
        b64 = images[0].get("data") or images[0].get("base64") or ""
        print(f"[imagine/generate auto] image preview: {_truncate(b64)}")
        assert len(b64) > 5000, f"image too small (likely mock stub): len={len(b64)}"


# ------- Cover generation -------
class TestImagineCover:
    def test_cover_real_image(self, api_client):
        payload = {
            "title": "Neon Drift",
            "genre": "racing",
            "lore": "Hovercraft racing through a neon-soaked metropolis.",
        }
        r = api_client.post(
            f"{BASE_URL}/api/imagine/cover", json=payload, timeout=LONG_TIMEOUT
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:500]}"
        data = r.json()
        assert data.get("status") == "success", f"status not success: {data}"
        images = data.get("images") or []
        assert len(images) > 0, "no images returned"
        b64 = images[0].get("data") or images[0].get("base64") or ""
        print(f"[imagine/cover] image preview: {_truncate(b64)}")
        assert len(b64) > 5000, f"cover image too small (likely mock stub): len={len(b64)}"


# ------- TTS: ai_reader.speak (query params) -------
class TestReaderSpeak:
    def test_reader_speak_real_audio(self, api_client):
        # Endpoint expects query params
        params = {
            "text": "Welcome to Galaxy Studio. Let's build something splendid.",
            "voice": "onyx",
            "speed": "1.0",
        }
        r = api_client.post(
            f"{BASE_URL}/api/reader/speak", params=params, timeout=LONG_TIMEOUT
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:500]}"
        data = r.json()
        b64 = data.get("audio_base64") or ""
        fmt = data.get("format") or data.get("audio_format") or ""
        print(f"[reader/speak] format={fmt} audio preview: {_truncate(b64)}")
        # Silent WAV stub was ~60 bytes; real mp3 should be in the thousands
        assert len(b64) > 2000, f"audio too small (likely silent stub): len={len(b64)}"
        assert "mp3" in (fmt or "").lower() or fmt == "", f"unexpected format: {fmt}"


# ------- TTS: jeeves/speak (body) -------
class TestJeevesSpeak:
    def test_jeeves_speak_real_audio(self, api_client):
        payload = {"text": "Splendid work, old chap. The kingdom prospers."}
        r = api_client.post(
            f"{BASE_URL}/api/jeeves/speak", json=payload, timeout=LONG_TIMEOUT
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:500]}"
        data = r.json()
        b64 = data.get("audio_base64") or ""
        print(f"[jeeves/speak] audio preview: {_truncate(b64)}")
        assert len(b64) > 2000, f"audio too small (likely silent stub): len={len(b64)}"


# ------- Jeeves Voice Trailer: 3 beats with audio + optional auto cover -------
class TestJeevesVoiceTrailer:
    def test_trailer_three_voiced_beats(self, api_client):
        payload = {"title": "Neon Drift", "theme": "a neon city"}
        r = api_client.post(
            f"{BASE_URL}/api/jeeves-voice/trailer",
            json=payload,
            timeout=LONG_TIMEOUT * 2,  # 3 TTS + maybe 1 image
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:500]}"
        data = r.json()
        clips = data.get("clips") or data.get("beats") or []
        assert len(clips) >= 3, f"expected >=3 beats, got {len(clips)}: keys={list(data.keys())}"
        for i, c in enumerate(clips[:3]):
            b64 = c.get("audio_base64") or ""
            print(f"[trailer beat {i}] audio preview: {_truncate(b64)}")
            assert len(b64) > 1500, f"trailer beat {i} audio too small: {len(b64)}"
        # Optional cover improvement check (not required to be present)
        has_cover = data.get("has_cover")
        cover = data.get("cover")
        print(f"[trailer] has_cover={has_cover}, cover present={bool(cover)}")
        # No assertion on cover — should just not error if absent
