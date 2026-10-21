"""Adversarial production raster/scene tests for Jeeves' source-bound sprite forge."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import unittest

from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_sprite_forge import (
    StudioSpriteError, _decode_verified_png, compile_authored_sprite,
)
from skeleton.jeeves.ai.studio_sprite_godot_resources import (
    SpriteResourceError, compile_godot_sprite_resources,
    verify_godot_sprite_resources,
)
from skeleton.jeeves.ai.studio_sprite_verify import (
    SpriteVerificationError, verify_published_sprite,
)
from skeleton.testing.test_jeeves_studio_sprite_forge import original_record


def reseal(record: dict) -> dict:
    record["source_sha256"] = digest([
        record["record_id"], record["facet"], record["revision"],
        record["document"], record["depends_on"],
    ])
    return record


def advanced() -> dict:
    record = original_record()
    record["document"]["atlas"] = {
        "columns": 1,
        "padding_px": 1, "extrude_edges": True,
        "power_of_two": True, "alpha_threshold": 1,
        "pivot_px": [1, 1],
    }
    return reseal(record)


class SpriteQualityTests(unittest.TestCase):
    def test_legacy_atlas_remains_byte_deterministic(self):
        first = compile_authored_sprite(original_record())
        second = compile_authored_sprite(original_record())
        self.assertEqual(first["png"], second["png"])
        self.assertEqual(first["metadata"], second["metadata"])
        self.assertEqual(first["metadata"]["sheet_width_px"], 8)
        self.assertEqual(first["metadata"]["sheet_height_px"], 4)
        self.assertEqual(first["metadata"]["frames"][0]["rect_px"], [0, 0, 4, 4])

    def test_verified_multiline_atlas_power_of_two_and_gutters(self):
        record = advanced()
        out = compile_authored_sprite(record)
        meta = out["metadata"]
        self.assertEqual((meta["sheet_width_px"], meta["sheet_height_px"]),
                         (8, 16))
        self.assertEqual([item["rect_px"] for item in meta["frames"]], [
            [1, 1, 4, 4], [1, 7, 4, 4],
        ])
        self.assertEqual(meta["atlas_geometry"]["padding_px"], 1)
        self.assertTrue(meta["atlas_geometry"]["power_of_two"])
        self.assertTrue(meta["atlas_geometry"]["extrude_edges"])
        verified = verify_published_sprite(out["png"], meta)
        self.assertTrue(verified["layout_and_padding_reproduced"])
        self.assertEqual(verified["source_frames_verified"], 2)
        self.assertEqual(verified["collision_masks_verified"], 2)

    def test_collision_mask_contains_real_bitmapped_pixels(self):
        out = compile_authored_sprite(advanced())
        frames = out["metadata"]["frames"]
        self.assertEqual(frames[0]["collision_mask_bits_hex"], "06")
        self.assertEqual(frames[1]["collision_mask_bits_hex"], "06")
        self.assertEqual(frames[0]["opaque_source_pixels"], 2)
        self.assertEqual(frames[0]["opaque_bounds_px"], [0, 0, 4, 4])
        self.assertEqual(frames[0]["pivot_px"], [2, 2])
        self.assertEqual(
            frames[0]["collision_mask_sha256"],
            sha256(bytes.fromhex("06")).hexdigest(),
        )

    def test_source_pixel_rgba_not_premultiplied(self):
        record = advanced()
        record["document"]["palette"][1] = "#ff800080"
        out = compile_authored_sprite(reseal(record))
        pixels = _decode_verified_png(
            out["png"], out["metadata"]["sheet_width_px"],
            out["metadata"]["sheet_height_px"],
        )
        fw = out["metadata"]["sheet_width_px"] * 4
        self.assertEqual(pixels[1 * fw + 3 * 4:1 * fw + 4 * 4],
                         bytes.fromhex("ff800080"))
        self.assertEqual(out["metadata"]["atlas_geometry"]["alpha_encoding"],
                         "straight_rgba_no_premultiplication")

    def test_straight_transparent_edge_must_not_bleed_hidden_rgb(self):
        record = advanced()
        record["document"]["palette"][0] = "#ff000000"
        with self.assertRaisesRegex(StudioSpriteError, "zero RGB"):
            compile_authored_sprite(reseal(record))

    def test_zero_gutter_rejects_edge_extrusion(self):
        record = advanced()
        record["document"]["atlas"]["padding_px"] = 0
        with self.assertRaisesRegex(StudioSpriteError, "positive texture gutter"):
            compile_authored_sprite(reseal(record))

    def test_pivot_outside_original_bounds_is_rejected(self):
        record = advanced()
        record["document"]["atlas"]["pivot_px"] = [2, 0]
        with self.assertRaisesRegex(StudioSpriteError, "pivot"):
            compile_authored_sprite(reseal(record))

    def test_atlas_layout_declared_fields_are_strict(self):
        record = advanced()
        del record["document"]["atlas"]["alpha_threshold"]
        with self.assertRaisesRegex(StudioSpriteError, "all geometry policies"):
            compile_authored_sprite(reseal(record))

    def test_reconstructed_pixel_can_not_be_changed_without_detection(self):
        out = compile_authored_sprite(advanced())
        image = bytearray(out["png"])
        image[-4] ^= 0x01
        with self.assertRaises(SpriteVerificationError):
            verify_published_sprite(bytes(image), out["metadata"])

    def test_forged_alpha_mask_and_refreshed_receipt_is_detected(self):
        out = compile_authored_sprite(advanced())
        forged = deepcopy(out["metadata"])
        forged["frames"][0]["collision_mask_bits_hex"] = "ff"
        forged["frames"][0]["collision_mask_sha256"] = sha256(b"\xff").hexdigest()
        original = dict(forged)
        original.pop("receipt_sha256")
        forged["receipt_sha256"] = digest(original)
        with self.assertRaisesRegex(SpriteVerificationError, "frame evidence"):
            verify_published_sprite(out["png"], forged)

    def test_invalid_source_revision_rejected_without_forging(self):
        record = original_record()
        record["document"]["width"] = 3
        with self.assertRaisesRegex(StudioSpriteError, "content differs"):
            compile_authored_sprite(record)

    def test_objective_art_grade_is_grounded_without_claiming_human_review(self):
        out = compile_authored_sprite(advanced())
        report = out["metadata"]["objective_quality"]
        self.assertEqual(report["objective_quality_score_0_100"], 100)
        self.assertEqual(report["visible_source_pixels"], 4)
        self.assertEqual(report["total_source_pixels"], 8)
        self.assertEqual(report["alpha_coverage_millionths"], 500000)
        self.assertFalse(report["manual_art_review_complete"])
        self.assertFalse(report["originality_and_copyright_review_complete"])
        self.assertFalse(report["subjective_artistic_quality_proven"])

    def test_weak_animation_creates_objective_warning_and_lower_grade(self):
        record = advanced()
        record["document"]["frames"][1]["pixels"] = [0, 1, 1, 0]
        result = compile_authored_sprite(reseal(record))
        report = result["metadata"]["objective_quality"]
        self.assertIn("no_visible_animation_frame_variation",
                      report["objective_risk_flags"])
        self.assertLess(report["objective_quality_score_0_100"], 100)

    def test_quality_score_forgery_is_rejected_even_if_receipt_is_rehashed(self):
        out = compile_authored_sprite(advanced())
        forged = deepcopy(out["metadata"])
        forged["objective_quality"]["objective_quality_score_0_100"] = 999
        forged["objective_quality"]["receipt_sha256"] = digest({
            key: value for key, value in forged["objective_quality"].items()
            if key != "receipt_sha256"
        })
        forged["receipt_sha256"] = digest({
            key: value for key, value in forged.items()
            if key != "receipt_sha256"
        })
        with self.assertRaisesRegex(SpriteVerificationError, "quality signals"):
            verify_published_sprite(out["png"], forged)

    def test_godot_resource_is_live_engine_atlas_and_timed_animation(self):
        sprite = compile_authored_sprite(advanced())
        paths = compile_godot_sprite_resources(sprite["metadata"])
        self.assertIn("game/frontier/sprites/hero-idle.tres", paths)
        resource = paths["game/frontier/sprites/hero-idle.tres"]
        scene = paths["game/frontier/sprites/hero-idle.tscn"]
        self.assertIn('[gd_resource type="SpriteFrames"', resource)
        self.assertIn("AtlasTexture", resource)
        self.assertIn("region = Rect2(1, 1, 4, 4)", resource)
        self.assertIn('name": &"idle"', resource)
        self.assertIn('duration": 1.200000', resource)
        self.assertIn('type="AnimatedSprite2D"', scene)
        self.assertIn('sprite_frames = ExtResource("1")', scene)
        self.assertFalse(
            verify_godot_sprite_resources(
                sprite["metadata"], paths,
            )["in_engine_loaded_and_rendered"]
        )

    def test_godot_resource_verification_rejects_wrong_animation_timing(self):
        sprite = compile_authored_sprite(advanced())
        paths = compile_godot_sprite_resources(sprite["metadata"])
        name = "game/frontier/sprites/hero-idle.tres"
        changed = {**paths, name: paths[name].replace("1.200000", "5.000000")}
        with self.assertRaisesRegex(SpriteResourceError, "differs"):
            verify_godot_sprite_resources(sprite["metadata"], changed)

    def test_standalone_sprite_resources_have_correct_root(self):
        sprite = compile_authored_sprite(original_record())
        sources = compile_godot_sprite_resources(
            sprite["metadata"], directory="sprites",
        )
        self.assertIn('res://sprites/hero-idle.png', sources["sprites/hero-idle.tres"])
        self.assertIn('res://sprites/hero-idle.tres', sources["sprites/hero-idle.tscn"])
        self.assertTrue(
            verify_godot_sprite_resources(
                sprite["metadata"], sources, directory="sprites",
            )["source_resource_reproducible"]
        )

    def test_portability_refuses_illegal_windows_sprite_filename(self):
        record = original_record()
        record["document"]["asset_id"] = "sprite:name"
        with self.assertRaisesRegex(StudioSpriteError, "portable"):
            compile_authored_sprite(reseal(record))

    def test_transparent_sprite_has_no_opaque_collision_hitbox(self):
        record = original_record()
        record["document"]["frames"][0]["pixels"] = [0, 0, 0, 0]
        out = compile_authored_sprite(reseal(record))
        first = out["metadata"]["frames"][0]
        self.assertIsNone(first["opaque_bounds_px"])
        self.assertEqual(first["opaque_source_pixels"], 0)
        self.assertEqual(first["collision_mask_bits_hex"], "00")

    def test_padded_surface_unowned_regions_remain_transparent(self):
        out = compile_authored_sprite(advanced())
        meta = out["metadata"]
        rgba = _decode_verified_png(
            out["png"], meta["sheet_width_px"], meta["sheet_height_px"],
        )
        width = meta["sheet_width_px"]
        # An 8x16 image with 1 gutter and two vertical frames, the final POT
        # transparent region after x=5 must remain empty throughout.
        for y in range(meta["sheet_height_px"]):
            for x in range(6, meta["sheet_width_px"]):
                at = (y * width + x) * 4
                self.assertEqual(rgba[at:at + 4], b"\x00\x00\x00\x00")


if __name__ == "__main__":
    unittest.main()
