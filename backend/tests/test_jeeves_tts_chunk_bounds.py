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
