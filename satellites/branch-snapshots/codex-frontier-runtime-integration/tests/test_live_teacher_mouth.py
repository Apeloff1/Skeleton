"""Tests for live teacher mouth binding.

Covers phoneme-to-viseme mapping, smoothing, blend shape computation,
and real-time feed behavior.
"""
from __future__ import annotations

import pytest

from skeleton.intelligence.live_teacher_mouth import LiveMouthBinding, MouthTarget, VISeme_MAP


class TestVISemeMap:
    def test_basic_mappings(self):
        assert VISeme_MAP["AA"] == "ah"
        assert VISeme_MAP["B"] == "mb"
        assert VISeme_MAP["S"] == "s"
        assert VISeme_MAP["sil"] == "sil"

    def test_unknown_phoneme(self):
        assert VISeme_MAP.get("XYZ", "sil") == "sil"


class TestMouthTarget:
    def test_target_creation(self):
        target = MouthTarget(viseme="ah", weight=0.8)
        assert target.viseme == "ah"
        assert target.weight == 0.8

    def test_target_to_dict(self):
        target = MouthTarget(viseme="oh", weight=0.6, blend_shapes={"jaw_open": 0.4})
        d = target.to_dict()
        assert d["viseme"] == "oh"
        assert d["blend_shapes"]["jaw_open"] == 0.4


class TestLiveMouthBinding:
    def test_creation(self):
        mouth = LiveMouthBinding(smoothing_window=3)
        assert mouth.smoothing_window == 3

    def test_feed_silence(self):
        mouth = LiveMouthBinding()
        target = mouth.feed_phoneme("sil", 0.0)
        assert target.viseme == "sil"
        assert target.weight == 0.0

    def test_feed_phoneme(self):
        mouth = LiveMouthBinding()
        target = mouth.feed_phoneme("AA", 100.0)
        assert target.viseme == "ah"
        assert target.weight > 0

    def test_smoothing(self):
        mouth = LiveMouthBinding(smoothing_window=3)
        # Feed same phoneme multiple times
        for i in range(5):
            mouth.feed_phoneme("AA", i * 40.0)
        target = mouth.feed_phoneme("AA", 200.0)
        assert target.viseme == "ah"
        assert target.weight > 0.5  # Should be confident after many same phonemes

    def test_blend_shapes_ah(self):
        mouth = LiveMouthBinding()
        target = mouth.feed_phoneme("AA", 100.0, confidence=1.0)
        assert "jaw_open" in target.blend_shapes
        assert target.blend_shapes["jaw_open"] > 0

    def test_blend_shapes_mb(self):
        mouth = LiveMouthBinding()
        target = mouth.feed_phoneme("B", 100.0)
        assert target.viseme == "mb"
        assert "lip_pucker" in target.blend_shapes

    def test_current_matches_last_feed(self):
        mouth = LiveMouthBinding()
        mouth.feed_phoneme("IY", 100.0)
        current = mouth.current()
        assert current.viseme == "ee"

    def test_card(self):
        mouth = LiveMouthBinding()
        mouth.feed_phoneme("AA", 100.0)
        card = mouth.card()
        assert card["kind"] == "live-mouth-binding-card"
        assert card["current_viseme"] == "ah"
        assert card["history_len"] > 0

    def test_history_trimming(self):
        mouth = LiveMouthBinding()
        # Feed many phonemes over time
        for i in range(20):
            mouth.feed_phoneme("AA", i * 50.0)
        # History should be trimmed to ~200ms window
        assert mouth._history[0][0] >= 900.0  # last - 200ms
