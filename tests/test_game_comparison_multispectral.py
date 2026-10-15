"""CPU-bounded non-reconstructive native motion/spectral feature contracts."""
from __future__ import annotations

import hashlib
import math
import struct
import unittest

from skeleton.jeeves.game_comparison_multispectral import (
    SCHEMA,describe_native_spatial_change,
    describe_native_spectral_audio,
    summarize_multispectral_change,native_step_multispectral_receipt,
)


def frame(rgb,width=8,height=8):
    return bytes(rgb)*(width*height)


class MultispectralNativeSignalContracts(unittest.TestCase):
    def test_four_by_four_grid_detects_real_rgb_change(self):
        before=frame((0,0,0))
        after=before[:]
        changed=bytearray(after)
        for row in range(4):
            for col in range(4):
                at=(row*8+col)*3
                changed[at:at+3]=bytes((255,255,255))
        measured=describe_native_spatial_change(before,bytes(changed),8,8)
        self.assertEqual(measured["coarse_grid_rows"],4)
        self.assertEqual(len(measured["tile_mean_rgb_differences"]),16)
        self.assertEqual(measured["overall_changed_pixel_fraction"],0.25)
        self.assertFalse(measured["camera_motion_or_player_movement_inferred"])

    def test_spectral_pcm_is_aggregate_and_does_not_label_music(self):
        silent=describe_native_spectral_audio(b"",44100)
        self.assertEqual(silent["normalized_bin_index_centroid"],0)
        self.assertFalse(silent["sample_emits_frequency_energy"])
        wave=b"".join(
            struct.pack("<hh",int(7000*math.sin(2*math.pi*i/32)),
                        int(7000*math.sin(2*math.pi*i/32)))
            for i in range(512)
        )
        active=describe_native_spectral_audio(wave,44100)
        self.assertTrue(active["sample_emits_frequency_energy"])
        self.assertEqual(len(active["normalized_spectral_bin_energy"]),8)
        self.assertFalse(active["sound_effect_music_or_voice_recognized"])
        self.assertFalse(active["original_audio_or_music_copied"])

    def test_native_video_pcm_hashes_bind_feature_receipt(self):
        before=frame((5,10,20))
        after=frame((20,40,60))
        pcm=struct.pack("<hh",2000,-2000)*128
        last={"width":8,"height":8}
        current={
            "width":8,"height":8,"sample_rate":32000,
            "pixel_sha256":hashlib.sha256(after).hexdigest(),
            "audio_sha256":hashlib.sha256(pcm).hexdigest(),
        }
        receipt=native_step_multispectral_receipt(
            last,before,current,after,pcm,
        )
        self.assertEqual(receipt["schema_version"],SCHEMA)
        self.assertEqual(receipt["spatial_status"],
                         "measured_same_geometry_native_frame_delta")
        self.assertIsNotNone(receipt["spatial"])
        self.assertEqual(receipt["source_frame_sha256"],current["pixel_sha256"])
        self.assertFalse(receipt["visual_frames_copied"])
        with self.assertRaises(ValueError):
            native_step_multispectral_receipt(
                last,before,current,frame((20,41,60)),pcm,
            )

    def test_geometry_changes_are_not_falsely_called_motion(self):
        after=frame((10,20,30))
        pcm=b""
        current={
            "width":8,"height":8,"sample_rate":44100,
            "pixel_sha256":hashlib.sha256(after).hexdigest(),
            "audio_sha256":hashlib.sha256(pcm).hexdigest(),
        }
        report=native_step_multispectral_receipt(
            {"width":4,"height":4},
            frame((1,2,3),4,4),current,after,pcm,
        )
        self.assertIsNone(report["spatial"])
        self.assertEqual(report["spatial_status"],
                         "not_comparable_before_frame_or_geometry_changed")

    def test_audio_spatial_comparisons_are_observations_only(self):
        a={
            "spatial":describe_native_spatial_change(
                frame((1,2,3)),frame((2,3,4)),8,8,
            ),
            "spectral_audio":describe_native_spectral_audio(b"",44100),
        }
        b={
            "spatial":describe_native_spatial_change(
                frame((1,2,3)),frame((200,200,200)),8,8,
            ),
            "spectral_audio":describe_native_spectral_audio(
                struct.pack("<hh",1000,1000)*64,44100,
            ),
        }
        result=summarize_multispectral_change(a,b)
        self.assertGreater(result["mean_rgb_motion_absolute_difference"],0)
        self.assertFalse(result["meaningful_gameplay_mechanic_inferred"])
        self.assertFalse(result["model_weights_promoted"])


if __name__=="__main__":
    unittest.main()
