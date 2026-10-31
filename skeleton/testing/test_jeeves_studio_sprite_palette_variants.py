"""Original pixel-palette skins: authored source, actual PNGs, immutable alpha."""
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
from skeleton.jeeves.ai.studio_sprite_zip_verify import (
    SpritePackageVerificationError, verify_published_sprite_package,
)
from skeleton.jeeves.ai.studio_sprite_palette_variants import (
    SpritePaletteVariantError, compile_original_palette_variant,
    compile_original_palette_collection, verify_original_palette_variant,
)
from skeleton.testing.test_jeeves_studio_sprite_forge import original_record


def skin(original: dict | None = None, *,
         color_map: dict[str, str] | None = None) -> dict:
    original = original or original_record()
    document = {
        "kind": "sprite_palette_variant",
        "asset_id": "hero-night",
        "parent_record_id": original["record_id"],
        "color_map": color_map or {"#ff0000ff": "#3366ffff"},
    }
    record = {
        "record_id": "night-recolor",
        "facet": "sprite_forge",
        "revision": 1,
        "depends_on": [original["record_id"]],
        "document": document,
    }
    record["source_sha256"] = digest([
        record["record_id"], "sprite_forge", 1,
        document, record["depends_on"],
    ])
    return record


def reseal(item: dict) -> dict:
    item["source_sha256"] = digest([
        item["record_id"], item["facet"], item["revision"],
        item["document"], item["depends_on"],
    ])
    return item


class OriginalPaletteVariantTests(unittest.TestCase):
    def test_actual_recolored_png_contains_explicit_rgb_and_original_alpha(self):
        source = original_record()
        result = compile_original_palette_variant(source, skin(source))
        proof = result["palette_variant_receipt"]
        self.assertEqual(result["metadata"]["asset_id"], "hero-night")
        self.assertEqual(proof["original_source_revision_sha256"],
                         source["source_sha256"])
        self.assertNotEqual(proof["source_png_sha256"], proof["derived_png_sha256"])
        self.assertTrue(proof["unchanged_collision_masks_verified"])
        self.assertTrue(proof["unchanged_frame_timings_verified"])
        self.assertFalse(proof["model_repaint_performed"])
        self.assertTrue(
            result["palette_variant_pixel_replay"]["all_rgba_mapping_policies_satisfied"]
        )

    def test_full_pixel_replay_rejects_silent_png_changes(self):
        original = original_record()
        output = compile_original_palette_variant(original, skin(original))
        fake = deepcopy(output)
        fake["png"] = fake["png"] + b"silently-corrupted"
        from skeleton.jeeves.ai.studio_sprite_forge import compile_authored_sprite
        with self.assertRaises(SpritePaletteVariantError):
            verify_original_palette_variant(
                compile_authored_sprite(original),
                fake, output["palette_variant_receipt"],
            )

    def test_palette_skin_preserves_all_collision_rectangles(self):
        original = original_record()
        from skeleton.jeeves.ai.studio_sprite_forge import compile_authored_sprite
        source = compile_authored_sprite(original)
        variant = compile_original_palette_variant(original, skin(original))
        self.assertEqual(source["collision_rectangles"]["frames"],
                         variant["collision_rectangles"]["frames"])
        self.assertEqual(source["metadata"]["animations"],
                         variant["metadata"]["animations"])

    def test_alpha_edits_forbidden_before_saving_source(self):
        original = original_record()
        modified = skin(original, color_map={"#ff0000ff": "#3366ff88"})
        with self.assertRaisesRegex(SpritePaletteVariantError, "collision alpha"):
            compile_original_palette_variant(original, modified)

    def test_unseen_palette_color_is_refused(self):
        original = original_record()
        modified = skin(original, color_map={"#123456ff": "#3366ffff"})
        with self.assertRaisesRegex(SpritePaletteVariantError, "absent"):
            compile_original_palette_variant(original, modified)

    def test_transparent_hidden_rgb_cannot_be_reintroduced(self):
        original = original_record()
        modified = skin(original, color_map={"#00000000": "#ff000000"})
        with self.assertRaisesRegex(SpritePaletteVariantError, "transparent"):
            compile_original_palette_variant(original, modified)

    def test_foreign_source_revision_is_refused(self):
        original = original_record()
        modified = skin(original)
        modified["source_sha256"] = "a" * 64
        with self.assertRaisesRegex(SpritePaletteVariantError, "source hash"):
            compile_original_palette_variant(original, modified)

    def test_no_dependent_parent_source_is_refused(self):
        original = original_record()
        modified = skin(original)
        modified["depends_on"] = []
        with self.assertRaisesRegex(SpritePaletteVariantError, "depend"):
            compile_original_palette_variant(original, reseal(modified))

    def test_skinned_frame_ids_and_durations_are_original(self):
        original = original_record()
        output = compile_original_palette_variant(original, skin(original))
        self.assertEqual(
            [x["duration_ms"] for x in output["metadata"]["frames"]],
            [120, 150],
        )
        self.assertEqual(
            output["metadata"]["animations"][0]["frame_ids"],
            ["idle-0", "idle-1"],
        )

    def test_same_palette_variant_bytes_are_reproducible(self):
        original = original_record()
        first = compile_original_palette_variant(original, skin(original))
        second = compile_original_palette_variant(original, skin(original))
        self.assertEqual(first, second)

    def test_collision_with_existing_native_asset_id_rejected(self):
        original = original_record()
        other = skin(original)
        other["document"]["asset_id"] = "hero-idle"
        with self.assertRaisesRegex(SpritePaletteVariantError, "distinct"):
            compile_original_palette_variant(original, reseal(other))

    def test_project_compiles_both_original_and_derived_png(self):
        original = original_record()
        variant = skin(original)
        collection = compile_original_palette_collection({
            original["record_id"]: original,
            variant["record_id"]: variant,
        })
        self.assertEqual(collection["count"], 2)
        self.assertEqual(len(collection["palette_variant_receipts"]), 1)
        self.assertEqual(
            {entry["metadata"]["asset_id"] for entry in collection["assets"]},
            {"hero-idle", "hero-night"},
        )


class PersistentPaletteSkinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.exports = self.root / "exports"
        self.exports.mkdir()
        self.store = CreatorProjectSourceStore(
            self.root / "original-source.sqlite",
            project_id="original-game", export_root=self.exports,
        )
        self.addCleanup(self.store.close)

    def create(self, record_id, document, deps=None):
        return self.store.create(build_creator_command(
            "create", project_id="original-game",
            payload={"intent": {
                "record_id": record_id, "facet": "sprite_forge",
                "document": document, "depends_on": deps or [],
            }},
        ))

    def test_real_source_store_exports_both_native_png_and_godot_animations(self):
        original = original_record()
        parent = self.create("hero-source", original["document"])
        variant = self.create("night-recolor", skin(original)["document"],
                              deps=["hero-source"])
        exported = self.store.export(build_creator_command(
            "export", project_id="original-game",
            payload={"format": "sprite-atlas-zip", "artifact_name": "hero-skins"},
        ))
        self.assertNotEqual(parent["source_sha256"], variant["source_sha256"])
        with zipfile.ZipFile(self.exports / exported["artifact_name"]) as archive:
            names = set(archive.namelist())
            self.assertIn("sprites/hero-idle.png", names)
            self.assertIn("sprites/hero-night.png", names)
            self.assertIn("sprites/hero-night.tres", names)
            self.assertIn("sprites/hero-night.tscn", names)
            package = json.loads(archive.read("jeeves_sprite_receipt.json"))
            self.assertEqual(len(package["palette_variant_receipts"]), 1)
            self.assertEqual(package["asset_count"], 2)
            self.assertEqual(package["palette_variant_receipts"][0][
                "variant_source_revision_sha256"
            ], variant["source_sha256"])
            self.assertNotEqual(
                sha256(archive.read("sprites/hero-idle.png")).hexdigest(),
                sha256(archive.read("sprites/hero-night.png")).hexdigest(),
            )

    def test_independent_disk_archive_replays_all_saved_skin_pixels(self):
        original = original_record()
        self.create("hero-source", original["document"])
        self.create("night-recolor", skin(original)["document"],
                    deps=["hero-source"])
        exported = self.store.export(build_creator_command(
            "export", project_id="original-game",
            payload={"format": "sprite-atlas-zip", "artifact_name": "night"},
        ))
        path = self.exports / exported["artifact_name"]
        replay = verify_published_sprite_package(
            path, project_id="original-game",
            source_head_sha256=self.store.head_identity(),
            expected_archive_sha256=exported["artifact_sha256"],
        )
        self.assertEqual(replay["asset_count"], 2)
        self.assertEqual(replay["palette_variants_replayed"], 1)
        self.assertTrue(replay["all_rgba_hitbox_and_resource_bytes_replayed"])
        self.assertEqual(replay["receipt_sha256"],
                         exported["disk_verification"]["receipt_sha256"])

    def test_modified_inside_zip_fails_even_with_correct_new_archive_hash(self):
        original = original_record()
        self.create("hero-source", original["document"])
        self.create("night-recolor", skin(original)["document"],
                    deps=["hero-source"])
        exported = self.store.export(build_creator_command(
            "export", project_id="original-game",
            payload={"format": "sprite-atlas-zip", "artifact_name": "night"},
        ))
        original_path = self.exports / exported["artifact_name"]
        tampered = self.root / "tampered-original-game.zip"
        with zipfile.ZipFile(original_path) as source:
            with zipfile.ZipFile(tampered, "w") as writer:
                for info in source.infolist():
                    content = source.read(info.filename)
                    if info.filename == "sprites/hero-night.png":
                        content += b"modified-native-pixels"
                    writer.writestr(info, content)
        with self.assertRaises(SpritePackageVerificationError):
            verify_published_sprite_package(
                tampered, project_id="original-game",
                source_head_sha256=self.store.head_identity(),
                expected_archive_sha256=sha256(tampered.read_bytes()).hexdigest(),
            )

    def test_invalid_palette_skin_denied_before_sqlite_commit(self):
        original = original_record()
        self.create("hero-source", original["document"])
        bad = skin(original, color_map={"#ff0000ff": "#12345600"})
        with self.assertRaises(SpritePaletteVariantError):
            self.create("night-recolor", bad["document"], deps=["hero-source"])
        self.assertEqual(self.store.snapshot()["source_count"], 1)

    def test_parent_palette_edit_cannot_break_approved_skin(self):
        original = original_record()
        self.create("hero-source", original["document"])
        self.create("night-recolor", skin(original)["document"],
                    deps=["hero-source"])
        with self.assertRaises(SpritePaletteVariantError):
            self.store.edit(build_creator_command(
                "edit", project_id="original-game",
                payload={
                    "target_id": "hero-source", "expected_revision": 1,
                    "patch": {"set": {
                        "palette": ["#00000000", "#ccccccff", "#00ff00ff"],
                    }, "remove": []},
                },
            ))
        self.assertEqual(self.store._records["hero-source"]["revision"], 1)
        self.assertEqual(self.store._records["night-recolor"]["revision"], 1)


if __name__ == "__main__":
    unittest.main()
