"""Adversarial authored heightfield normal-map and export regression tests."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_creator_source import CreatorProjectSourceStore
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_sprite_forge import (
    _decode_verified_png, compile_authored_sprite,
)
from skeleton.jeeves.ai.studio_sprite_surface import (
    SpriteSurfaceError, verify_authored_normals,
    verify_normal_texture_bytes,
)
from skeleton.jeeves.ai.studio_sprite_godot_resources import (
    SpriteResourceError, compile_godot_sprite_resources,
    verify_godot_sprite_resources,
)
from skeleton.jeeves.ai.studio_sprite_zip_verify import (
    SpritePackageVerificationError, verify_published_sprite_package,
)
from skeleton.testing.test_jeeves_studio_sprite_forge import original_record


def lit_original() -> dict:
    record = original_record()
    record["document"]["lighting"] = {
        "kind": "heightfield_normals", "strength": 8,
        "height_frames": [
            {"frame_id": "idle-0", "heights": [0, 90, 140, 255]},
            {"frame_id": "idle-1", "heights": [255, 140, 90, 0]},
        ],
    }
    record["source_sha256"] = digest([
        record["record_id"], record["facet"], record["revision"],
        record["document"], record["depends_on"],
    ])
    return record


def reseal(record: dict) -> dict:
    record["source_sha256"] = digest([
        record["record_id"], record["facet"], record["revision"],
        record["document"], record["depends_on"],
    ])
    return record


class HeightfieldNormalTests(unittest.TestCase):
    def test_heightfield_produces_real_lossless_png_with_matching_dimensions(self):
        result = compile_authored_sprite(lit_original())
        metadata = result["metadata"]
        normal = result["normal_png"]
        self.assertTrue(normal.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(sha256(normal).hexdigest(),
                         metadata["normal_map"]["normal_png_sha256"])
        self.assertEqual(metadata["sheet_width_px"], 8)
        self.assertEqual(metadata["sheet_height_px"], 4)
        self.assertEqual(
            len(_decode_verified_png(normal, 8, 4)), 8 * 4 * 4,
        )
        self.assertFalse(metadata["normal_map"]["normal_map_loaded_in_native_engine"])

    def test_flat_heightfields_produce_forward_facing_normal(self):
        record = lit_original()
        for frame in record["document"]["lighting"]["height_frames"]:
            frame["heights"] = [100, 100, 100, 100]
        result = compile_authored_sprite(reseal(record))
        pixels = _decode_verified_png(result["normal_png"], 8, 4)
        # The original transparent source pixel remains transparent.
        self.assertEqual(pixels[:4], bytes(4))
        # A source-red pixel gets forward-facing tangent-space normal (128,128,255).
        self.assertEqual(pixels[8:12], bytes((128, 128, 255, 255)))

    def test_generated_normal_map_preserves_exact_source_alpha(self):
        result = compile_authored_sprite(lit_original())
        colors = _decode_verified_png(result["png"], 8, 4)
        normals = _decode_verified_png(result["normal_png"], 8, 4)
        self.assertEqual(colors[3::4], normals[3::4])
        self.assertTrue(verify_normal_texture_bytes(
            result["png"], result["normal_png"], result["metadata"]["normal_map"],
            width=8, height=4,
        )["normalized_visible_vectors_verified"])

    def test_heightfield_replay_reproduces_normal_png_and_proof(self):
        source = lit_original()
        result = compile_authored_sprite(source)
        proof = verify_authored_normals(
            source["document"]["lighting"],
            metadata=result["metadata"],
            color_png=result["png"], normal_png=result["normal_png"],
            normal_receipt=result["metadata"]["normal_map"],
        )
        self.assertTrue(proof["height_map_replayed"])
        self.assertFalse(proof["native_lighting_observed"])

    def test_one_pixel_source_edit_changes_normal_identity(self):
        a = lit_original()
        b = deepcopy(a)
        b["document"]["lighting"]["height_frames"][0]["heights"][1] = 25
        changed = compile_authored_sprite(reseal(b))
        original = compile_authored_sprite(a)
        self.assertNotEqual(original["normal_png"], changed["normal_png"])
        self.assertNotEqual(
            original["metadata"]["normal_map"]["receipt_sha256"],
            changed["metadata"]["normal_map"]["receipt_sha256"],
        )

    def test_heightfield_missing_a_frame_is_rejected(self):
        source = lit_original()
        source["document"]["lighting"]["height_frames"].pop()
        with self.assertRaisesRegex(SpriteSurfaceError, "match every authored"):
            compile_authored_sprite(reseal(source))

    def test_heightfield_rejects_boolean_pixel_and_floating_strength(self):
        source = lit_original()
        source["document"]["lighting"]["height_frames"][0]["heights"][0] = True
        with self.assertRaisesRegex(SpriteSurfaceError, "8-bit"):
            compile_authored_sprite(reseal(source))
        source = lit_original()
        source["document"]["lighting"]["strength"] = 2.5
        with self.assertRaisesRegex(SpriteSurfaceError, "integer"):
            compile_authored_sprite(reseal(source))

    def test_heightfield_rejects_duplicate_frame_identity(self):
        source = lit_original()
        source["document"]["lighting"]["height_frames"][1]["frame_id"] = "idle-0"
        with self.assertRaises(SpriteSurfaceError):
            compile_authored_sprite(reseal(source))

    def test_pixel_scale_preserves_identical_source_normals(self):
        result = compile_authored_sprite(lit_original())
        pixels = _decode_verified_png(result["normal_png"], 8, 4)
        def texel(x, y):
            return pixels[(y * 8 + x) * 4:(y * 8 + x + 1) * 4]
        self.assertEqual(texel(2, 0), texel(3, 0))
        self.assertEqual(texel(2, 0), texel(2, 1))
        self.assertNotEqual(texel(2, 0), texel(4, 0))

    def test_power_two_atlas_gutters_replay_exact_authored_normals(self):
        record = lit_original()
        record["document"]["atlas"] = {
            "columns": 1, "padding_px": 1, "extrude_edges": True,
            "power_of_two": True, "alpha_threshold": 1,
            "pivot_px": [1, 1],
        }
        result = compile_authored_sprite(reseal(record))
        meta = result["metadata"]
        self.assertEqual(
            [meta["sheet_width_px"], meta["sheet_height_px"]], [8, 16],
        )
        self.assertTrue(verify_authored_normals(
            record["document"]["lighting"], metadata=meta,
            color_png=result["png"], normal_png=result["normal_png"],
            normal_receipt=meta["normal_map"],
        )["height_map_replayed"])
        self.assertTrue(verify_normal_texture_bytes(
            result["png"], result["normal_png"], meta["normal_map"],
            width=8, height=16,
        )["normalized_visible_vectors_verified"])

    def test_normal_png_tampering_cannot_repass_published_verification(self):
        result = compile_authored_sprite(lit_original())
        corrupted = bytearray(result["normal_png"])
        corrupted[-5] ^= 1
        with self.assertRaises(SpriteSurfaceError):
            verify_normal_texture_bytes(
                result["png"], bytes(corrupted), result["metadata"]["normal_map"],
                width=8, height=4,
            )

    def test_normal_map_forged_proof_rejected_even_with_matching_png(self):
        result = compile_authored_sprite(lit_original())
        proof = dict(result["metadata"]["normal_map"])
        proof["normal_map_loaded_in_native_engine"] = True
        proof["receipt_sha256"] = digest({
            k: v for k, v in proof.items() if k != "receipt_sha256"
        })
        with self.assertRaises(SpriteSurfaceError):
            verify_normal_texture_bytes(
                result["png"], result["normal_png"], proof,
                width=8, height=4,
            )

    def test_no_lighting_source_does_not_generate_unrequested_normals(self):
        result = compile_authored_sprite(original_record())
        self.assertIsNone(result["normal_png"])
        self.assertNotIn("normal_map", result["metadata"])

    def test_godot_canvas_texture_binds_exact_reviewed_normal_atlas(self):
        metadata = compile_authored_sprite(lit_original())["metadata"]
        resources = compile_godot_sprite_resources(metadata)
        source = resources["game/frontier/sprites/hero-idle.tres"]
        self.assertIn('[sub_resource type="CanvasTexture" id="CanvasSurface"]', source)
        self.assertIn('normal_texture = ExtResource("2")', source)
        self.assertIn('atlas = SubResource("CanvasSurface")', source)
        self.assertIn('hero-idle.normal.png', source)
        verification = verify_godot_sprite_resources(metadata, resources)
        self.assertTrue(verification["canvas_normal_resource_compiled"])
        self.assertEqual(
            verification["normal_image_sha256"],
            metadata["normal_map"]["normal_png_sha256"],
        )
        self.assertFalse(verification["in_engine_loaded_and_rendered"])

    def test_unlit_sprites_preserve_diffuse_only_atlas_contract(self):
        meta = compile_authored_sprite(original_record())["metadata"]
        resources = compile_godot_sprite_resources(meta, directory="sprites")
        source = resources["sprites/hero-idle.tres"]
        self.assertNotIn("CanvasTexture", source)
        self.assertNotIn("normal.png", source)
        self.assertIn('atlas = ExtResource("1")', source)

    def test_forged_normal_proof_cannot_be_bound_to_engine_resources(self):
        meta = deepcopy(compile_authored_sprite(lit_original())["metadata"])
        meta["normal_map"]["color_png_sha256"] = "0" * 64
        with self.assertRaises(SpriteResourceError):
            compile_godot_sprite_resources(meta)

    def test_canvas_surface_resource_substitution_is_not_accepted(self):
        meta = compile_authored_sprite(lit_original())["metadata"]
        resources = compile_godot_sprite_resources(meta)
        path = "game/frontier/sprites/hero-idle.tres"
        tampered = dict(resources)
        tampered[path] = tampered[path].replace(
            'normal_texture = ExtResource("2")',
            'normal_texture = ExtResource("1")',
        )
        with self.assertRaises(SpriteResourceError):
            verify_godot_sprite_resources(meta, tampered)

    def test_source_store_exports_verified_normal_png_with_sprite(self):
        source = lit_original()
        with TemporaryDirectory() as folder:
            root = Path(folder)
            exports = root / "exports"
            exports.mkdir()
            with CreatorProjectSourceStore(
                root / "game.sqlite", project_id="original-game", export_root=exports,
            ) as owner:
                owner.create(build_creator_command(
                    "create", project_id="original-game",
                    payload={"intent": {
                        "record_id": "hero-source", "facet": "sprite_forge",
                        "document": source["document"], "depends_on": [],
                    }},
                ))
                result = owner.export(build_creator_command(
                    "export", project_id="original-game",
                    payload={"format": "sprite-atlas-zip", "artifact_name": "hero"},
                ))
                with zipfile.ZipFile(exports / result["artifact_name"]) as z:
                    normal = z.read("sprites/hero-idle.normal.png")
                    color = z.read("sprites/hero-idle.png")
                    metadata = json.loads(z.read("sprites/hero-idle.json"))
                    original_heights = json.loads(
                        z.read("sprites/hero-idle.normal.source.json")
                    )
                self.assertTrue(verify_authored_normals(
                    original_heights, metadata=metadata,
                    color_png=color, normal_png=normal,
                    normal_receipt=metadata["normal_map"],
                )["height_map_replayed"])
                self.assertTrue(verify_normal_texture_bytes(
                    color, normal, metadata["normal_map"],
                    width=metadata["sheet_width_px"],
                    height=metadata["sheet_height_px"],
                )["pixel_alpha_preserved"])


if __name__ == "__main__":
    unittest.main()
