"""Tests for live teacher mouth binding."""
from __future__ import annotations

import pytest

from skeleton.intelligence.live_teacher_mouth import LiveMouthBinding, MouthTarget, VISeme_MAP


class TestVISemeMap:
    def test_all_phonemes_mapped(self):
        for phoneme in ["AA", "B", "CH", "D", "EH", "F", "G", "IH", "JH", "K", "L", "M", "N", "OW", "P", "R", "S", "T", "UH", "V", "W", "Y", "Z"]:
            assert phoneme in VISeme_MAP

    def test_silence(self):
        assert VISeme_MAP["sil"] == "sil"


class TestMouthTarget:
    def test_to_dict(self):
        t = MouthTarget(viseme="ah", weight=0.8, blend_shapes={"jaw_open": 0.6})
        d = t.to_dict()
        assert d["viseme"] == "ah"
        assert d["weight"] == 0.8
        assert d["blend_shapes"]["jaw_open"] == 0.6


class TestLiveMouthBinding:
    def test_feed_phoneme_silence(self):
        mouth = LiveMouthBinding()
        result = mouth.feed_phoneme("sil", 0.0)
        assert result.viseme == "sil"
        assert result.weight < 1.0

    def test_feed_phoneme_ah(self):
        mouth = LiveMouthBinding()
        result = mouth.feed_phoneme("AA", 0.0)
        assert result.viseme == "ah"
        assert "jaw_open" in result.blend_shapes

    def test_feed_phoneme_ee(self):
        mouth = LiveMouthBinding()
        result = mouth.feed_phoneme("IY", 0.0)
        assert result.viseme == "ee"
        assert result.blend_shapes["lip_wide"] > 0

    def test_feed_phoneme_oh(self):
        mouth = LiveMouthBinding()
        result = mouth.feed_phoneme("OW", 0.0)
        assert result.viseme == "oh"
        assert result.blend_shapes["lip_round"] > 0

    def test_smoothing(self):
        mouth = LiveMouthBinding(smoothing_window=3)
        # Feed same phoneme multiple times
        for i in range(5):
            result = mouth.feed_phoneme("AA", i * 40.0)
        assert result.viseme == "ah"
        assert result.weight > 0.5

    def test_confidence_scaling(self):
        mouth = LiveMouthBinding()
        result_high = mouth.feed_phoneme("AA", 0.0, confidence=1.0)
        result_low = mouth.feed_phoneme("AA", 0.0, confidence=0.5)
        assert result_high.weight > result_low.weight

    def test_current(self):
        mouth = LiveMouthBinding()
        mouth.feed_phoneme("AA", 0.0)
        current = mouth.current()
        assert current.viseme == "ah"

    def test_card(self):
        mouth = LiveMouthBinding()
        mouth.feed_phoneme("AA", 0.0)
        card = mouth.card()
        assert card["kind"] == "live-mouth-binding-card"
        assert card["current_viseme"] == "ah"
