"""Regression tests for deterministic, bounded Jeeves narration delivery."""
from __future__ import annotations

import asyncio
import math

import pytest

from core import expressive_tts as tts


@pytest.mark.parametrize("speed", [float("nan"), float("inf"), -float("inf"), "nan", "1e999", True, "unknown"])
def test_invalid_speeds_rejected_before_engine_access(monkeypatch, speed):
    def forbidden():
        raise AssertionError("engine client accessed before speed validation")

    monkeypatch.setattr(tts.EngineClient, "from_env", forbidden)
    with pytest.raises(ValueError, match="speed"):
        asyncio.run(tts.generate_expressive_tts("Good morning.", speed_override=speed))


@pytest.mark.parametrize("speed,expected", [(0.01, 0.25), (0.5, 0.5), (5.0, 4.0)])
def test_finite_speed_preserves_bounded_clamp(monkeypatch, speed, expected):
    recorded = {}

    class FakeClient:
        async def synthesize_speech(self, **kwargs):
            recorded.update(kwargs)
            return {"audio": b"mp3"}

    monkeypatch.setattr(tts.EngineClient, "from_env", lambda: FakeClient())
    result = asyncio.run(tts.generate_expressive_tts("Hello world", speed_override=speed))
    assert math.isclose(recorded["speed"], expected)
    assert math.isclose(result["speed"], expected)
    assert result["spoken_text"]


@pytest.mark.parametrize("bound", [0, -1, True, 1.5, 4097])
def test_narration_rejects_invalid_chunk_budget(bound):
    with pytest.raises(ValueError, match="max_chars"):
        tts.chunk_for_narration("Hello world.", bound)


def test_narration_long_unbroken_word_is_not_oversized():
    source = "x" * 10001
    pieces = tts.chunk_for_narration(source, max_chars=700)
    assert all(0 < len(piece) <= 700 for piece in pieces)
    assert "".join(pieces) == source


def test_narration_sentence_aware_roundtrip_preserves_word_order():
    source = "Hello there. A very long sentence " + ("with many words " * 100) + "done! Next?"
    pieces = tts.chunk_for_narration(source, max_chars=90)
    assert all(0 < len(piece) <= 90 for piece in pieces)
    assert " ".join(" ".join(pieces).split()) == " ".join(source.split())


def test_narration_returns_no_chunks_for_whitespace():
    assert tts.chunk_for_narration(" \t\n ") == []


def test_single_character_chunk_budget_always_makes_progress():
    chunks = tts.chunk_for_narration("abcdefgh", max_chars=1)
    assert chunks == list("abcdefgh")



@pytest.mark.parametrize("voice", [
    " Nova", "alloy ", "UPPERCASE", "\n", "../../etc/passwd",
    "voice with spaces", "x" * 65, True, {"voice": "nova"},
])
def test_invalid_voice_fails_before_engine_access(monkeypatch, voice):
    monkeypatch.setattr(
        tts.EngineClient, "from_env",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected engine call")),
    )
    with pytest.raises(ValueError, match="voice"):
        asyncio.run(tts.generate_expressive_tts("Hello", voice_override=voice))


@pytest.mark.parametrize("tone", [True, 42, {"tone": "dramatic"}])
def test_nontext_tone_is_rejected_before_engine(monkeypatch, tone):
    monkeypatch.setattr(
        tts.EngineClient, "from_env",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected engine call")),
    )
    with pytest.raises(ValueError, match="tone"):
        asyncio.run(tts.generate_expressive_tts("Hello", tone=tone))


@pytest.mark.parametrize("text", [None, 42, ["hello"], {"text": "hello"}])
def test_invalid_text_is_rejected_before_engine(monkeypatch, text):
    monkeypatch.setattr(
        tts.EngineClient, "from_env",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected engine call")),
    )
    with pytest.raises(ValueError, match="text"):
        asyncio.run(tts.generate_expressive_tts(text))


@pytest.mark.parametrize("shape", ["false", 0, None, []])
def test_invalid_shaping_flag_does_not_fall_through_to_truthy(monkeypatch, shape):
    monkeypatch.setattr(
        tts.EngineClient, "from_env",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected engine call")),
    )
    with pytest.raises(ValueError, match="shaping"):
        asyncio.run(tts.generate_expressive_tts("Hello", shape=shape))


def test_valid_voice_override_reaches_canonical_engine(monkeypatch):
    recorded = {}
    class Client:
        async def synthesize_speech(self, **kwargs):
            recorded.update(kwargs)
            return {"audio": b"valid mp3"}

    monkeypatch.setattr(tts.EngineClient, "from_env", lambda: Client())
    result = asyncio.run(tts.generate_expressive_tts(
        "Hello", voice_override="nova", shape=False
    ))
    assert recorded["voice"] == "nova"
    assert result["voice"] == "nova"
    assert result["audio_base64"]


@pytest.mark.parametrize("response", [None, [], "not-a-dict", {}, {"audio": b""}, {"audio": "not-bytes"}])
def test_invalid_engine_audio_contract_has_controlled_error(monkeypatch, response):
    class Client:
        async def synthesize_speech(self, **_kwargs):
            return response

    monkeypatch.setattr(tts.EngineClient, "from_env", lambda: Client())
    with pytest.raises(tts.EngineClientError):
        asyncio.run(tts.generate_expressive_tts("Hello"))


def test_engine_media_size_limit_is_enforced_before_base64(monkeypatch):
    monkeypatch.setattr(tts, "MAX_ENGINE_AUDIO_BYTES", 3)
    class Client:
        async def synthesize_speech(self, **_kwargs):
            return {"audio": b"oversized mp3"}

    monkeypatch.setattr(tts.EngineClient, "from_env", lambda: Client())
    with pytest.raises(tts.EngineClientError, match="media budget"):
        asyncio.run(tts.generate_expressive_tts("Hello"))


def test_narration_text_and_chunk_budgets_are_fail_closed(monkeypatch):
    monkeypatch.setattr(tts, "MAX_NARRATION_TEXT_CHARS", 10)
    with pytest.raises(ValueError, match="text budget"):
        tts.chunk_for_narration("x" * 11, max_chars=1)
    monkeypatch.setattr(tts, "MAX_NARRATION_CHUNKS", 3)
    with pytest.raises(ValueError, match="chunk count"):
        tts.chunk_for_narration("abcdefgh", max_chars=1)


@pytest.mark.parametrize("value", [1, True, {}, []])
def test_invalid_emotional_state_is_rejected(value):
    with pytest.raises(ValueError, match="emotional state"):
        tts.emotion_to_tone(value)
