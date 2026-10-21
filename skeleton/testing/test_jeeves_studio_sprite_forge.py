"""Executable original sprite PNG tests for Jeeves' actual game asset forge."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
import zipfile

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_creator_source import (CreatorProjectSourceStore, CreatorSourceError)
from skeleton.jeeves.ai.studio_sprite_forge import (
    StudioSpriteError, _decode_verified_png, compile_authored_sprite,
    compile_sprite_collection,
)


def original_sprite() -> dict:
    return {
        "kind": "pixel_sprite",
        "asset_id": "hero-idle",
        "width": 2, "height": 2, "pixel_scale": 2,
        "palette": ["#00000000", "#ff0000ff", "#00ff00ff"],
        "frames": [
            {"frame_id": "idle-0", "duration_ms": 120,
             "pixels": [0, 1, 1, 0]},
            {"frame_id": "idle-1", "duration_ms": 150,
             "pixels": [0, 2, 2, 0]},
        ],
        "animations": [
            {"name": "idle", "frame_ids": ["idle-0", "idle-1"], "loop": True},
            {"name": "pose", "frame_ids": ["idle-0"], "loop": False},
        ],
    }


def original_record() -> dict:
    content = original_sprite()
    return {
        "record_id": "hero-source", "facet": "sprite_forge", "revision": 1,
        "source_sha256": digest([
            "hero-source", "sprite_forge", 1, content, [],
        ]),
        "depends_on": [], "document": content,
    }


class SpriteForgeTests(unittest.TestCase):
    def test_rgba_png_is_real_and_losslessly_matches_authored_frames(self):
        result = compile_authored_sprite(original_record())
        image, proof = result["png"], result["metadata"]
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(proof["sheet_width_px"], 8)
        self.assertEqual(proof["sheet_height_px"], 4)
        rgba = _decode_verified_png(image, 8, 4)
        self.assertEqual(rgba[:4], bytes.fromhex("00000000"))
        self.assertEqual(rgba[8:12], bytes.fromhex("ff0000ff"))
        self.assertEqual(rgba[16:20], bytes.fromhex("00000000"))
        self.assertEqual(rgba[24:28], bytes.fromhex("00ff00ff"))
        self.assertEqual(proof["png_sha256"], sha256(image).hexdigest())
        self.assertEqual(sha256(rgba).hexdigest(), proof["pixel_content_sha256"])
        self.assertTrue(proof["pixels_losslessly_verified"])

    def test_frame_durations_and_animation_loop_are_real(self):
        proof = compile_authored_sprite(original_record())["metadata"]
        self.assertEqual(proof["frames"][0]["rect_px"], [0, 0, 4, 4])
        self.assertEqual(proof["frames"][1]["rect_px"], [4, 0, 4, 4])
        self.assertEqual(proof["animations"][0]["duration_ms"], 270)
        self.assertTrue(proof["animations"][0]["loop"])
        self.assertFalse(proof["animations"][1]["loop"])
        self.assertFalse(proof["native_engine_sprite_binding_verified"])
        self.assertFalse(proof["generated_with_model_image_weights"])

    def test_deterministic_sprite_generation(self):
        first = compile_authored_sprite(original_record())
        second = compile_authored_sprite(original_record())
        self.assertEqual(first, second)

    def test_invalid_pixel_index_is_refused_not_imputed(self):
        record = original_record()
        record["document"]["frames"][0]["pixels"][0] = 256
        with self.assertRaises(StudioSpriteError):
            compile_authored_sprite(record)

    def test_invalid_palette_requires_explicit_rgba(self):
        record = original_record()
        record["document"]["palette"][1] = "#1234"
        with self.assertRaises(StudioSpriteError):
            compile_authored_sprite(record)

    def test_animation_must_reference_existent_frames(self):
        record = original_record()
        record["document"]["animations"][0]["frame_ids"] = ["invented-frame"]
        with self.assertRaises(StudioSpriteError):
            compile_authored_sprite(record)

    def test_duplicate_frame_and_animation_names_rejected(self):
        record = original_record()
        record["document"]["frames"][1]["frame_id"] = "idle-0"
        with self.assertRaises(StudioSpriteError):
            compile_authored_sprite(record)
        record = original_record()
        record["document"]["animations"][1]["name"] = "idle"
        with self.assertRaises(StudioSpriteError):
            compile_authored_sprite(record)

    def test_generative_model_claims_not_added(self):
        result = compile_authored_sprite(original_record())
        self.assertFalse(result["metadata"]["generated_with_model_image_weights"])
        self.assertFalse(result["metadata"]["native_engine_sprite_binding_verified"])

    def test_foreign_non_sprite_facet_cannot_be_forged_into_sprite(self):
        record = original_record()
        record["facet"] = "story"
        with self.assertRaises(StudioSpriteError):
            compile_authored_sprite(record)

    def test_png_crc_tampering_does_not_verify(self):
        result = compile_authored_sprite(original_record())
        altered = bytearray(result["png"])
        altered[-9] ^= 0x01
        with self.assertRaises(StudioSpriteError):
            _decode_verified_png(bytes(altered), 8, 4)

    def test_two_sources_cannot_claim_one_sprite_identity(self):
        first = original_record()
        second = deepcopy(first)
        second["record_id"] = "other-hero"
        second["source_sha256"] = digest([
            "other-hero", "sprite_forge", 1, second["document"], [],
        ])
        with self.assertRaises(StudioSpriteError):
            compile_sprite_collection({
                "hero-source": first, "other-hero": second,
            })

    def test_pixel_budget_refuses_oversized_output(self):
        record = original_record()
        record["document"]["width"] = 64
        record["document"]["height"] = 64
        record["document"]["pixel_scale"] = 8
        record["document"]["frames"] = [
            {"frame_id": "idle-0", "duration_ms": 120,
             "pixels": [0] * (64 * 64)}
            for _ in range(64)
        ]
        with self.assertRaises(StudioSpriteError):
            compile_authored_sprite(record)


class PersistentSpriteExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.export_root = self.root / "exports"
        self.export_root.mkdir()
        self.store = CreatorProjectSourceStore(
            self.root / "sprites.sqlite", project_id="original-game",
            export_root=self.export_root,
        )
        self.addCleanup(self.store.close)

    def create_source(self):
        return self.store.create(build_creator_command(
            "create", project_id="original-game",
            payload={"intent": {
                "record_id": "hero-source",
                "facet": "sprite_forge",
                "document": original_sprite(),
                "depends_on": [],
            }},
        ))

    def export(self):
        return self.store.export(build_creator_command(
            "export", project_id="original-game",
            payload={"format": "sprite-atlas-zip", "artifact_name": "original-art"},
        ))

    def test_persisted_original_pixel_source_produces_true_png_zip(self):
        created = self.create_source()
        result = self.export()
        target = self.export_root / result["artifact_name"]
        self.assertEqual(target.suffix, ".zip")
        self.assertEqual(result["export_format"], "sprite-atlas-zip")
        self.assertEqual(sha256(target.read_bytes()).hexdigest(),
                         result["artifact_sha256"])
        disk = result["disk_verification"]
        self.assertTrue(disk["actual_archive_bytes_verified"])
        self.assertEqual(disk["source_head_sha256"],
                         created["history_sha256"])
        self.assertEqual(disk["archive_sha256"], result["artifact_sha256"])
        with zipfile.ZipFile(target) as archive:
            names = set(archive.namelist())
            self.assertEqual(names, {
                "sprites/hero-idle.png",
                "sprites/hero-idle.json",
                "jeeves_sprite_receipt.json",
            })
            proof = json.loads(archive.read("jeeves_sprite_receipt.json"))
            asset = json.loads(archive.read("sprites/hero-idle.json"))
            image = archive.read("sprites/hero-idle.png")
            self.assertEqual(asset["png_sha256"], sha256(image).hexdigest())
            self.assertEqual(asset["source_sha256"], created["source_sha256"])
            self.assertEqual(proof["source_head_sha256"],
                             created["history_sha256"])
            self.assertEqual(proof["asset_count"], 1)
            self.assertFalse(proof["native_engine_sprite_binding_verified"])
            self.assertEqual(len(_decode_verified_png(image, 8, 4)), 128)

    def test_reexport_is_identical_after_restart(self):
        self.create_source()
        first = self.export()
        self.store.close()
        self.store = CreatorProjectSourceStore(
            self.root / "sprites.sqlite", project_id="original-game",
            export_root=self.export_root,
        )
        second = self.export()
        self.assertEqual(second["artifact_sha256"], first["artifact_sha256"])
        self.assertTrue(second["already_exported"])
        self.assertEqual(len(list(self.export_root.iterdir())), 1)

    def test_no_sprite_record_means_no_synthetic_image(self):
        with self.assertRaises(StudioSpriteError):
            self.export()
        self.assertEqual(list(self.export_root.iterdir()), [])

    def test_mutation_changes_export_receipt_and_filename(self):
        self.create_source()
        first = self.export()
        self.store.edit(build_creator_command(
            "edit", project_id="original-game",
            payload={"target_id": "hero-source", "expected_revision": 1,
                     "patch": {"set": {"pixel_scale": 3}, "remove": []}},
        ))
        second = self.export()
        self.assertNotEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(len(list(self.export_root.iterdir())), 2)

    def test_corrupted_archive_identity_cannot_be_silently_replaced(self):
        self.create_source()
        first = self.export()
        target = self.export_root / first["artifact_name"]
        with target.open("ab") as stream:
            stream.write(b"externally-altered")
        with self.assertRaises(CreatorSourceError):
            self.export()


if __name__ == "__main__":
    unittest.main()
