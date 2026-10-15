"""CPU-bounded native audiovisual descriptor unit tests; no game assets required."""
from __future__ import annotations

import math
import struct
import unittest

from skeleton.jeeves.game_comparison_signal_features import (
    compare_native_texture, describe_native_audio, describe_native_frame,
)


class NativeTextureFeatureContracts(unittest.TestCase):
    def test_black_vs_white_frame_entropy(self):
        black=describe_native_frame(bytes((0,0,0))*16,4,4)
        white=describe_native_frame(bytes((255,255,255))*16,4,4)
        self.assertEqual(black["dark_pixel_fraction"],1.0)
        self.assertEqual(white["bright_pixel_fraction"],1.0)
        self.assertEqual(black["luminance_entropy_bits"],0.0)
        self.assertFalse(black["gameplay_semantics_inferred"])

    def test_empty_audio_does_not_claim_music_classification(self):
        out=describe_native_audio(b"",44100)
        self.assertFalse(out["audio_emitted"])
        self.assertEqual(out["silence_fraction"],1.0)
        self.assertFalse(out["music_style_or_emotion_recognized"])

    def test_stereo_audio_texture(self):
        pcm=b"".join(struct.pack("<hh",1000,-1000) for _ in range(512))
        out=describe_native_audio(pcm,48000)
        self.assertTrue(out["audio_emitted"])
        self.assertEqual(out["sampled_frames"],512)
        self.assertAlmostEqual(out["stereo_energy_imbalance"],0.0)
        self.assertGreater(out["rms_left"],0)

    def test_comparison_contains_finite_differences(self):
        black={
            "video":describe_native_frame(bytes((0,0,0))*16,4,4),
            "audio":describe_native_audio(b"",44100),
        }
        white={
            "video":describe_native_frame(bytes((255,255,255))*16,4,4),
            "audio":describe_native_audio(struct.pack("<hh",4000,4000)*32,44100),
        }
        comparison=compare_native_texture(black,white)
        self.assertIsNone(comparison["quality_or_music_style_winner"])
        self.assertGreater(comparison["video_dark_pixel_fraction_absolute_difference"],0)
        self.assertGreater(comparison["audio_rms_mono_absolute_difference"],0)
        self.assertTrue(all(
            math.isfinite(value) for key,value in comparison.items()
            if key.endswith("_absolute_difference")
        ))


if __name__=="__main__":
    unittest.main()
