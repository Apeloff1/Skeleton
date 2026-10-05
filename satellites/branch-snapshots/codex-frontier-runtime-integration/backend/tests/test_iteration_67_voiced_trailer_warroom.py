"""
Iteration 67 — Voiced Game Trailer + War-Room tone tagging.

Tests:
- POST /api/jeeves-voice/trailer (with full payload + with empty payload)
- POST /api/jeeves-voice/narrate (chunking, success clips)
- GET  /api/jeeves-voice/cast (11 agents, each with tone/voice)
- GET  /api/jeeves-voice/voice/tones (>=12 tones)
- POST /api/jeeves-voice/voice/speak (butler tone, real HD audio)
- War-Room sanity: groupchat router still loaded → /api/health 200
"""

import os
import time
import requests
import pytest

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/")
JV = f"{BASE_URL}/api/jeeves-voice"

# TTS calls take ~3-8s per beat → trailer can take ~25s total
TIMEOUT = 90


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Backend health / war-room sanity ────────────────────────────────────────
class TestHealthAndWarRoom:
    def test_health_200(self, client):
        r = client.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200, r.text

    def test_groupchat_router_imports_agent_cast(self):
        """War-Room sanity — _say() pulls tone from AGENT_CAST."""
        from routes import groupchat as gc
        from routes.jeeves_voice import AGENT_CAST
        # AGENT_CAST is imported by groupchat (war-room transcript tone tagging)
        assert hasattr(gc, "_say"), "groupchat._say missing"
        assert "Jeeves" in AGENT_CAST and "tone" in AGENT_CAST["Jeeves"]


# ── Voice cast & tones (catalog endpoints) ─────────────────────────────────
class TestCastAndTones:
    def test_cast_returns_11_agents_each_with_tone_voice(self, client):
        r = client.get(f"{JV}/cast", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "cast" in data
        cast = data["cast"]
        assert len(cast) == 11, f"expected 11 agents, got {len(cast)}"
        for entry in cast:
            assert entry.get("agent")
            assert entry.get("tone"), f"missing tone for {entry.get('agent')}"
            assert entry.get("voice"), f"missing voice for {entry.get('agent')}"
            assert "speed" in entry

    def test_voice_tones_has_12_presets(self, client):
        r = client.get(f"{JV}/voice/tones", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "tones" in data and "default" in data
        assert len(data["tones"]) >= 12, f"expected >=12 tones, got {len(data['tones'])}"
        assert data["default"] == "butler"


# ── /voice/speak regression (single tone, real HD audio) ───────────────────
class TestVoiceSpeakRegression:
    def test_voice_speak_butler_returns_audio(self, client):
        payload = {"text": "Good day. Welcome to the lab.", "tone": "butler"}
        r = client.post(f"{JV}/voice/speak", json=payload, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "success", f"status={data.get('status')} err={data.get('error')}"
        assert data.get("audio_base64"), "audio_base64 empty"
        assert len(data["audio_base64"]) > 1000, "audio_base64 suspiciously short"


# ── /narrate — chunked, sentence-bounded HD audio ──────────────────────────
class TestNarrate:
    def test_narrate_chunks_more_than_one(self, client):
        payload = {
            "text": "Long text. Multiple sentences here. And more.",
            "tone": "narrator",
            "max_chars": 80,
        }
        r = client.post(f"{JV}/narrate", json=payload, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("chunks", 0) > 1, f"expected chunks>1, got {data.get('chunks')}"
        clips = data.get("clips") or []
        assert len(clips) == data["chunks"]
        # Every clip should be success with audio
        for i, c in enumerate(clips):
            assert c.get("status") == "success", f"clip[{i}] status={c.get('status')} err={c.get('error')}"
            assert c.get("audio_base64"), f"clip[{i}] missing audio"


# ── 🎬 /trailer — 3-beat multi-voice cinematic ─────────────────────────────
class TestTrailer:
    @staticmethod
    def _assert_three_beat_trailer(data):
        assert data.get("beats") == 3, f"expected beats=3, got {data.get('beats')}"
        clips = data.get("clips") or []
        assert len(clips) == 3
        expected_labels = ["Open", "Tension", "Title"]
        expected_tones = ["narrator", "dramatic", "triumphant"]
        for i, c in enumerate(clips):
            assert c.get("label") == expected_labels[i], f"clip[{i}] label={c.get('label')}"
            assert c.get("tone") == expected_tones[i], f"clip[{i}] tone={c.get('tone')}"
            assert c.get("status") == "success", (
                f"clip[{i}] status={c.get('status')} err={c.get('error')}"
            )
            assert c.get("audio_base64"), f"clip[{i}] missing audio_base64"
            assert len(c["audio_base64"]) > 1000, f"clip[{i}] audio too short"

    def test_trailer_with_full_payload(self, client):
        payload = {
            "title": "Neon Drifters",
            "theme": "a neon city",
            "lore": "When the grid went dark, only the drifters remembered the light.",
        }
        t0 = time.time()
        r = client.post(f"{JV}/trailer", json=payload, timeout=TIMEOUT)
        elapsed = time.time() - t0
        print(f"[trailer/full] {elapsed:.1f}s")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("title") == "Neon Drifters"
        assert data.get("theme") == "a neon city"
        self._assert_three_beat_trailer(data)

    def test_trailer_with_empty_payload_uses_defaults(self, client):
        t0 = time.time()
        r = client.post(f"{JV}/trailer", json={}, timeout=TIMEOUT)
        elapsed = time.time() - t0
        print(f"[trailer/empty] {elapsed:.1f}s")
        assert r.status_code == 200, r.text
        data = r.json()
        # Defaults should still produce a usable title + theme
        assert data.get("title")
        assert data.get("theme")
        self._assert_three_beat_trailer(data)
