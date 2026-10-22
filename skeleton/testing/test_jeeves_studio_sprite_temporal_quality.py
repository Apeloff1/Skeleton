"""Pixel-level temporal sprite QA and forged evidence regression tests."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import unittest

from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_sprite_forge import (
    _decode_verified_png, compile_authored_sprite,
)
from skeleton.jeeves.ai.studio_sprite_temporal_quality import (
    SpriteTemporalError, temporal_sprite_report,
)
from skeleton.jeeves.ai.studio_sprite_verify import (
    SpriteVerificationError, verify_published_sprite,
)
from skeleton.testing.test_jeeves_studio_sprite_forge import original_record


def reseal(source: dict) -> dict:
    source["source_sha256"] = digest([
        source["record_id"], source["facet"], source["revision"],
        source["document"], source["depends_on"],
    ])
    return source


class TestJeevesSpriteTemporalQuality(unittest.TestCase):
    def compile(self, source=None):
        return compile_authored_sprite(
            original_record() if source is None else reseal(source),
        )

    def test_original_frame_pixels_and_temporal_changes_are_measured(self):
        sprite = self.compile()
        report = sprite["metadata"]["temporal_quality"]
        self.assertEqual(report["original_frame_count"], 2)
        self.assertEqual(report["sampled_source_pixel_size"], [2, 2])
        self.assertEqual(len(report["per_frame"]), 2)
        self.assertEqual(
            report["per_frame"][0]["alpha_centroid_source_milli_px"],
            [1000, 1000],
        )
        self.assertEqual(
            report["per_frame"][1]["changed_source_pixels_since_prior"], 2,
        )
        self.assertEqual(
            report["per_frame"][1]["changed_alpha_pixels_since_prior"], 0,
        )
        self.assertIsNone(
            report["per_frame"][0]["changed_source_pixels_since_prior"],
        )

    def test_independently_replaying_emitted_png_verifies_all_timings(self):
        sprite = self.compile()
        meta = sprite["metadata"]
        rgba = _decode_verified_png(
            sprite["png"], meta["sheet_width_px"], meta["sheet_height_px"],
        )
        independently = temporal_sprite_report(rgba, meta)
        self.assertEqual(independently, meta["temporal_quality"])
        self.assertTrue(independently["full_alpha_and_color_frames_compared"])
        self.assertFalse(independently["native_frame_rendering_observed"])
        self.assertEqual(
            independently["decoded_atlas_rgba_sha256"],
            sha256(rgba).hexdigest(),
        )

    def test_duplicate_visual_frames_raise_review_warning_not_false_failure(self):
        record = original_record()
        record["document"]["frames"][1]["pixels"] = [0, 1, 1, 0]
        report = self.compile(record)["metadata"]["temporal_quality"]
        self.assertIn(
            "duplicate_consecutive_rgba_frames", report["review_warnings"],
        )
        self.assertEqual(
            report["per_frame"][1]["changed_source_pixels_since_prior"], 0,
        )

    def test_large_registered_alpha_shift_emits_objective_review_signal(self):
        record = original_record()
        record["document"]["frames"][0]["pixels"] = [1, 0, 0, 0]
        record["document"]["frames"][1]["pixels"] = [0, 0, 0, 2]
        report = self.compile(record)["metadata"]["temporal_quality"]
        self.assertIn(
            "large_alpha_centroid_shift_check_art_registration",
            report["review_warnings"],
        )
        self.assertGreater(
            report["per_frame"][1]["centroid_step_source_milli_px"], 750,
        )

    def test_transparent_frame_warns_without_claiming_pixel_jitter(self):
        record = original_record()
        record["document"]["frames"][0]["pixels"] = [0, 0, 0, 0]
        report = self.compile(record)["metadata"]["temporal_quality"]
        self.assertIn(
            "fully_transparent_authored_frame",
            report["review_warnings"],
        )
        self.assertIsNone(
            report["per_frame"][0]["alpha_centroid_source_milli_px"],
        )
        self.assertIsNone(
            report["per_frame"][1]["centroid_step_source_milli_px"],
        )

    def test_nonzero_unpremultiplied_alpha_is_weighted_exactly(self):
        record = original_record()
        record["document"]["palette"][1] = "#f19b3180"
        report = self.compile(record)["metadata"]["temporal_quality"]
        self.assertEqual(report["per_frame"][0]["alpha_weight_sum"], 256)

    def test_recompiling_same_original_frame_produces_same_temporal_hash(self):
        a = self.compile()
        b = self.compile()
        self.assertEqual(
            a["metadata"]["temporal_quality"]["receipt_sha256"],
            b["metadata"]["temporal_quality"]["receipt_sha256"],
        )

    def test_tampered_temporal_quality_score_with_rehashed_outer_meta_is_rejected(self):
        sprite = self.compile()
        tampered = deepcopy(sprite["metadata"])
        tampered["temporal_quality"]["per_frame"][1][
            "changed_source_pixels_since_prior"
        ] = 999
        tempor = dict(tampered["temporal_quality"])
        tempor.pop("receipt_sha256")
        tampered["temporal_quality"]["receipt_sha256"] = digest(tempor)
        top = dict(tampered)
        top.pop("receipt_sha256")
        tampered["receipt_sha256"] = digest(top)
        with self.assertRaisesRegex(SpriteVerificationError, "temporal quality"):
            verify_published_sprite(sprite["png"], tampered)

    def test_malformed_input_size_is_not_accepted_as_animation_evidence(self):
        sprite = self.compile()
        with self.assertRaises(SpriteTemporalError):
            temporal_sprite_report(b"\x00" * 12, sprite["metadata"])

    def test_missing_frame_geometry_refuses_to_guess_animations(self):
        sprite = self.compile()
        corrupted = deepcopy(sprite["metadata"])
        corrupted["frames"][1]["rect_px"] = [999, 0, 4, 4]
        rgba = _decode_verified_png(
            sprite["png"], sprite["metadata"]["sheet_width_px"],
            sprite["metadata"]["sheet_height_px"],
        )
        with self.assertRaises(SpriteTemporalError):
            temporal_sprite_report(rgba, corrupted)

    def test_one_frame_original_animation_is_supported(self):
        record = original_record()
        record["document"]["frames"] = [record["document"]["frames"][0]]
        record["document"]["animations"] = [
            {"name": "idle", "frame_ids": ["idle-0"], "loop": True},
        ]
        metadata = self.compile(record)["metadata"]
        report = metadata["temporal_quality"]
        self.assertEqual(report["original_frame_count"], 1)
        self.assertIsNone(
            report["per_frame"][0]["changed_source_pixels_since_prior"],
        )
        self.assertFalse(report["human_animation_quality_review_complete"])

    def test_optional_gutter_does_not_contaminate_source_temporal_pixels(self):
        record = original_record()
        record["document"]["atlas"] = {
            "columns": 1, "padding_px": 2,
            "extrude_edges": True, "power_of_two": True,
            "alpha_threshold": 1, "pivot_px": [1, 1],
        }
        sprite = self.compile(record)
        temporal = sprite["metadata"]["temporal_quality"]
        self.assertEqual(
            temporal["per_frame"][1]["changed_source_pixels_since_prior"], 2,
        )
        self.assertEqual(temporal["original_frame_count"], 2)


if __name__ == "__main__":
    unittest.main()
