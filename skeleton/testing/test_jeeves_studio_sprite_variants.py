"""Actual directional pixel-variant production, tamper and source integration."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
import json

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_creator_source import CreatorProjectSourceStore
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_sprite_forge import StudioSpriteError, compile_authored_sprite
from skeleton.jeeves.ai.studio_sprite_variants import (
    SpriteVariantError, derive_original_sprite_variants,
)
from skeleton.jeeves.ai.studio_sprite_verify import (
    SpriteVerificationError, verify_published_sprite,
)
from skeleton.testing.test_jeeves_studio_sprite_forge import original_record


def authored_variants() -> dict:
    record = original_record()
    record["document"]["variants"] = [
        {
            "frame_id": "left-0", "source_frame_id": "idle-0",
            "transform": "flip_horizontal", "duration_ms": 140,
        },
        {
            "frame_id": "up-1", "source_frame_id": "idle-1",
            "transform": "flip_vertical", "duration_ms": 160,
        },
        {
            "frame_id": "back-0", "source_frame_id": "idle-0",
            "transform": "rotate_180", "duration_ms": 130,
        },
    ]
    record["document"]["animations"].extend([
        {"name": "face-left", "frame_ids": ["left-0"], "loop": True},
        {"name": "face-up", "frame_ids": ["up-1"], "loop": True},
        {"name": "face-back", "frame_ids": ["back-0"], "loop": False},
    ])
    return reseal(record)


def reseal(record: dict) -> dict:
    record["source_sha256"] = digest([
        record["record_id"], record["facet"], record["revision"],
        record["document"], record["depends_on"],
    ])
    return record


class DirectionalSpriteTests(unittest.TestCase):
    def test_real_pixels_derive_exact_compass_frames(self):
        record = authored_variants()
        out = compile_authored_sprite(record)
        meta = out["metadata"]
        self.assertEqual(meta["original_authored_frame_count"], 2)
        self.assertEqual(len(meta["frames"]), 5)
        self.assertEqual([f["frame_id"] for f in meta["frames"]], [
            "idle-0", "idle-1", "left-0", "up-1", "back-0",
        ])
        self.assertEqual(out["independent_pixel_replay"][
            "lossless_directional_variants_verified"
        ], 3)
        self.assertEqual(meta["animations"][-1]["duration_ms"], 130)
        self.assertFalse(meta["derived_frame_proofs"][0]["artwork_generated_using_model"])
        self.assertEqual(sha256(out["png"]).hexdigest(), meta["png_sha256"])

    def test_repeated_original_compilation_is_bit_identical(self):
        record = authored_variants()
        self.assertEqual(compile_authored_sprite(record),
                         compile_authored_sprite(deepcopy(record)))

    def test_horizontal_flip_changes_original_authored_pixels_only(self):
        record = authored_variants()
        frames, _ = derive_original_sprite_variants(
            record["document"],
            colors=[bytes.fromhex(x[1:]) for x in record["document"]["palette"]],
            width=2, height=2,
        )
        self.assertEqual(frames[0]["pixels"], [0, 1, 1, 0])
        self.assertEqual(frames[2]["pixels"], [1, 0, 0, 1])
        self.assertEqual(frames[3]["pixels"], [2, 0, 0, 2])
        self.assertEqual(frames[4]["pixels"], [0, 1, 1, 0])

    def test_missing_parent_is_fatal_not_inferred(self):
        record = authored_variants()
        record["document"]["variants"][0]["source_frame_id"] = "imaginary"
        with self.assertRaisesRegex(StudioSpriteError, "original authored frame"):
            compile_authored_sprite(reseal(record))

    def test_variant_chains_are_forbidden(self):
        record = authored_variants()
        record["document"]["variants"][1]["source_frame_id"] = "left-0"
        with self.assertRaisesRegex(StudioSpriteError, "original authored frame"):
            compile_authored_sprite(reseal(record))

    def test_duplicate_derived_frame_identity_is_forbidden(self):
        record = authored_variants()
        record["document"]["variants"][0]["frame_id"] = "idle-1"
        with self.assertRaisesRegex(StudioSpriteError, "unique"):
            compile_authored_sprite(reseal(record))

    def test_transforms_are_explicit_lossless_subset(self):
        record = authored_variants()
        record["document"]["variants"][0]["transform"] = "bilinear_repaint"
        with self.assertRaisesRegex(StudioSpriteError, "lossy"):
            compile_authored_sprite(reseal(record))

    def test_unknown_transform_fields_rejected(self):
        record = authored_variants()
        record["document"]["variants"][0]["palette_swap"] = {"old": "new"}
        with self.assertRaisesRegex(StudioSpriteError, "exact geometry"):
            compile_authored_sprite(reseal(record))

    def test_tampered_variant_proof_rejected_even_if_metadata_resealed(self):
        output = compile_authored_sprite(authored_variants())
        forged = deepcopy(output["metadata"])
        forged["derived_frame_proofs"][0]["transform"] = "flip_vertical"
        internal = dict(forged["derived_frame_proofs"][0])
        internal.pop("receipt_sha256")
        forged["derived_frame_proofs"][0]["receipt_sha256"] = digest(internal)
        external = dict(forged)
        external.pop("receipt_sha256")
        forged["receipt_sha256"] = digest(external)
        with self.assertRaisesRegex(SpriteVerificationError, "directional"):
            verify_published_sprite(output["png"], forged)

    def test_source_sha_guard_also_applies_to_generated_animation(self):
        record = authored_variants()
        record["document"]["variants"][0]["duration_ms"] = 9999
        with self.assertRaisesRegex(StudioSpriteError, "source content differs"):
            compile_authored_sprite(record)

    def test_overbudget_variant_count_rejected(self):
        record = authored_variants()
        template = record["document"]["variants"][0]
        record["document"]["variants"] = [
            {**template, "frame_id": f"direction-{i}"}
            for i in range(63)
        ]
        with self.assertRaisesRegex(StudioSpriteError, "budget"):
            compile_authored_sprite(reseal(record))

    def test_source_owner_persists_original_plus_directional_variants(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            outroot = root / "exports"
            outroot.mkdir()
            with CreatorProjectSourceStore(
                root / "source.sqlite", project_id="sprite-game",
                export_root=outroot,
            ) as store:
                record = authored_variants()
                created = store.create(build_creator_command(
                    "create", project_id="sprite-game",
                    payload={"intent": {
                        "record_id": record["record_id"],
                        "facet": "sprite_forge",
                        "document": record["document"],
                        "depends_on": [],
                    }},
                ))
                self.assertEqual(created["source_sha256"], record["source_sha256"])
                receipt = store.export(build_creator_command(
                    "export", project_id="sprite-game",
                    payload={"format": "sprite-atlas-zip",
                             "artifact_name": "four-way-original-hero"},
                ))
                target = outroot / receipt["artifact_name"]
                self.assertEqual(sha256(target.read_bytes()).hexdigest(),
                                 receipt["artifact_sha256"])
                with zipfile.ZipFile(target) as z:
                    meta = json.loads(z.read("sprites/hero-idle.json"))
                    image = z.read("sprites/hero-idle.png")
                    tres = z.read("sprites/hero-idle.tres").decode()
                report = verify_published_sprite(image, meta)
                self.assertEqual(report["lossless_directional_variants_verified"], 3)
                self.assertIn('name": &"face-left"', tres)
                self.assertIn("Atlas_4", tres)


if __name__ == "__main__":
    unittest.main()
