"""Pixel-perfect original sprite collision compilation and source provenance tests."""
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
from skeleton.jeeves.ai.studio_sprite_forge import compile_authored_sprite
from skeleton.jeeves.ai.studio_sprite_hitboxes import (
    SpriteCollisionError, compile_exact_sprite_hitboxes,
    verify_exact_sprite_hitboxes,
)
from skeleton.testing.test_jeeves_studio_sprite_forge import original_record
from skeleton.testing.test_jeeves_studio_sprite_variants import authored_variants


def seal(record: dict) -> dict:
    record["source_sha256"] = digest([
        record["record_id"], record["facet"], record["revision"],
        record["document"], record["depends_on"],
    ])
    return record


class ExactSpriteCollisionTests(unittest.TestCase):
    def test_exact_diagonal_alpha_is_two_rectangles_not_a_bounding_box(self):
        out = compile_authored_sprite(original_record())
        collision = out["collision_rectangles"]
        self.assertEqual(collision["total_rectangles"], 4)
        first = collision["frames"][0]
        self.assertEqual(first["exact_source_rects"], [
            [1, 0, 1, 1], [0, 1, 1, 1],
        ])
        self.assertEqual(first["sprite_local_scaled_rects"], [
            [0, -2, 2, 2], [-2, 0, 2, 2],
        ])
        self.assertTrue(first["no_extra_or_missing_collision_pixels"])
        self.assertEqual(
            collision["source_sprite_receipt_sha256"],
            out["metadata"]["receipt_sha256"],
        )
        self.assertFalse(collision["godot_collision_nodes_instantiated"])

    def test_sparse_transparency_has_zero_collision_shapes(self):
        record = original_record()
        record["document"]["frames"][0]["pixels"] = [0, 0, 0, 0]
        out = compile_authored_sprite(seal(record))
        self.assertEqual(out["collision_rectangles"]["frames"][0]["rectangle_count"], 0)
        self.assertEqual(out["collision_rectangles"]["frames"][0]["exact_source_rects"], [])

    def test_fully_opaque_source_is_single_full_frame_rectangle(self):
        record = original_record()
        record["document"]["frames"][0]["pixels"] = [1, 1, 1, 1]
        out = compile_authored_sprite(seal(record))
        self.assertEqual(out["collision_rectangles"]["frames"][0][
            "exact_source_rects"
        ], [[0, 0, 2, 2]])

    def test_all_variants_receive_independent_alpha_rectangles(self):
        out = compile_authored_sprite(authored_variants())
        colliders = out["collision_rectangles"]
        self.assertEqual(len(colliders["frames"]), 5)
        self.assertEqual(colliders["total_rectangles"], 10)
        self.assertEqual(
            verify_exact_sprite_hitboxes(out["metadata"], colliders),
            colliders,
        )

    def test_repeated_geometry_is_fully_deterministic(self):
        record = original_record()
        first = compile_authored_sprite(record)
        second = compile_authored_sprite(record)
        self.assertEqual(first["collision_rectangles"], second["collision_rectangles"])

    def test_changing_rectangle_behind_receipt_is_refused(self):
        out = compile_authored_sprite(original_record())
        forged = deepcopy(out["collision_rectangles"])
        forged["frames"][0]["exact_source_rects"][0][0] = 0
        forged["receipt_sha256"] = digest({
            key: value for key, value in forged.items()
            if key != "receipt_sha256"
        })
        with self.assertRaisesRegex(SpriteCollisionError, "differs"):
            verify_exact_sprite_hitboxes(out["metadata"], forged)

    def test_changing_source_alpha_mask_hash_refuses_hitbox_compilation(self):
        out = compile_authored_sprite(original_record())
        changed = deepcopy(out["metadata"])
        changed["frames"][0]["collision_mask_sha256"] = "0" * 64
        changed["receipt_sha256"] = digest({
            key: value for key, value in changed.items()
            if key != "receipt_sha256"
        })
        with self.assertRaisesRegex(SpriteCollisionError, "SHA"):
            compile_exact_sprite_hitboxes(changed)

    def test_real_sqlite_authorized_sprite_export_publishes_hitbox_sidecar(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            exported = root / "output"
            exported.mkdir()
            with CreatorProjectSourceStore(
                root / "owner.sqlite", project_id="spr-world", export_root=exported,
            ) as store:
                record = authored_variants()
                store.create(build_creator_command(
                    "create", project_id="spr-world",
                    payload={"intent": {
                        "record_id": record["record_id"],
                        "facet": "sprite_forge",
                        "document": record["document"], "depends_on": [],
                    }},
                ))
                result = store.export(build_creator_command(
                    "export", project_id="spr-world",
                    payload={"format": "sprite-atlas-zip",
                             "artifact_name": "collision-and-art"},
                ))
                path = exported / result["artifact_name"]
                with zipfile.ZipFile(path) as archive:
                    names = archive.namelist()
                    self.assertIn("sprites/hero-idle.hitboxes.json", names)
                    hitboxes = json.loads(
                        archive.read("sprites/hero-idle.hitboxes.json")
                    )
                    meta = json.loads(archive.read("sprites/hero-idle.json"))
                    receipt = json.loads(archive.read("jeeves_sprite_receipt.json"))
                self.assertEqual(
                    receipt["collision_receipts"]["hero-idle"],
                    hitboxes["receipt_sha256"],
                )
                self.assertEqual(verify_exact_sprite_hitboxes(meta, hitboxes), hitboxes)
                self.assertEqual(
                    sha256(path.read_bytes()).hexdigest(), result["artifact_sha256"],
                )


if __name__ == "__main__":
    unittest.main()
