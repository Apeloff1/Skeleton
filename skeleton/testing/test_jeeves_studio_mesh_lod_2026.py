"""Adversarial authoring and publication tests for actual original GLB LODs."""
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
from skeleton.jeeves.ai.studio_original_mesh_lod import (
    OriginalMeshLodError, compile_original_mesh_lod_set,
    compile_original_mesh_lod_collection, verify_original_mesh_lod_set,
)
from skeleton.jeeves.ai.studio_original_mesh_godot import (
    OriginalMeshGodotError, compile_mesh_godot_resources,
    verify_mesh_godot_resources,
)
from skeleton.testing.test_jeeves_studio_asset_compilers_2026 import (
    mesh_record, reseal,
)


def source_mesh() -> dict:
    original = mesh_record("uv_sphere")
    original["document"]["segments"] = 32
    return reseal(original)


def lod_record() -> dict:
    document = {
        "kind": "procedural_mesh_lod_set",
        "base_record_id": "trial-model-source",
        "asset_id": "trial-mesh",
        "levels": [
            {"level": 1, "segments": 16, "switch_distance_mm": 8000},
            {"level": 2, "segments": 8, "switch_distance_mm": 22000},
        ],
    }
    return reseal({
        "record_id": "trial-mesh-lods",
        "facet": "asset_forge", "revision": 1,
        "depends_on": ["trial-model-source"],
        "document": document,
    })


class ParametricLodCompilerTests(unittest.TestCase):
    def setUp(self):
        self.base = source_mesh()
        self.author = lod_record()

    def render(self):
        return compile_original_mesh_lod_set(self.base, self.author)

    def test_two_lower_geometry_levels_are_actual_glb_bytes(self):
        compiled = self.render()
        self.assertEqual(len(compiled["levels"]), 2)
        triangles = [compiled["base"]["metadata"]["triangles"]] + [
            entry["metadata"]["triangles"] for entry in compiled["levels"]
        ]
        self.assertGreater(triangles[0], triangles[1])
        self.assertGreater(triangles[1], triangles[2])
        for record in compiled["levels"]:
            self.assertTrue(record["glb"].startswith(b"glTF"))
            self.assertEqual(
                sha256(record["glb"]).hexdigest(),
                record["metadata"]["glb_sha256"],
            )
            self.assertIn("source_sha256", record["derived_record"])

    def test_actual_lod_geometry_replays_from_approved_sources(self):
        assembled = self.render()
        checked = verify_original_mesh_lod_set(
            self.base, self.author, assembled["manifest"],
            {entry["metadata"]["asset_id"]: entry["glb"]
             for entry in assembled["levels"]},
        )
        self.assertEqual(checked["levels_replayed"], 2)
        self.assertTrue(checked["all_geometry_bytes_and_distances_replayed"])
        self.assertFalse(checked["engine_lod_switch_observed"])

    def test_source_output_is_deterministic(self):
        self.assertEqual(self.render(), self.render())

    def test_radial_cylinder_lods_are_supported(self):
        base = mesh_record("cylinder")
        base["document"]["segments"] = 32
        reseal(base)
        rendered = compile_original_mesh_lod_set(base, self.author)
        self.assertEqual(rendered["manifest"]["levels"][0]["segments"], 16)

    def test_reject_original_box_geometry_false_decimation(self):
        with self.assertRaises(OriginalMeshLodError):
            compile_original_mesh_lod_set(mesh_record("box"), self.author)

    def test_never_reinterpret_original_base_asset_name(self):
        altered = deepcopy(self.author)
        altered["document"]["asset_id"] = "different-model"
        with self.assertRaises(OriginalMeshLodError):
            compile_original_mesh_lod_set(self.base, reseal(altered))

    def test_levels_must_be_sequential_and_strictly_reduce_segments(self):
        for bad in (
            [
                {"level": 2, "segments": 16, "switch_distance_mm": 8000},
            ],
            [
                {"level": 1, "segments": 32, "switch_distance_mm": 8000},
            ],
            [
                {"level": 1, "segments": 16, "switch_distance_mm": 8000},
                {"level": 2, "segments": 20, "switch_distance_mm": 22000},
            ],
        ):
            authored = deepcopy(self.author)
            authored["document"]["levels"] = bad
            with self.assertRaises(OriginalMeshLodError):
                compile_original_mesh_lod_set(self.base, reseal(authored))

    def test_no_boolean_segments_or_distances(self):
        for field in ("segments", "switch_distance_mm"):
            changed = deepcopy(self.author)
            changed["document"]["levels"][0][field] = True
            with self.assertRaises(OriginalMeshLodError):
                compile_original_mesh_lod_set(self.base, reseal(changed))

    def test_missing_authored_dependencies_are_refused(self):
        altered = deepcopy(self.author)
        altered["depends_on"] = []
        with self.assertRaises(OriginalMeshLodError):
            compile_original_mesh_lod_set(self.base, reseal(altered))

    def test_distance_ordering_and_boundary_hysteresis_require_clear_stages(self):
        altered = deepcopy(self.author)
        altered["document"]["levels"][1]["switch_distance_mm"] = 8200
        with self.assertRaises(OriginalMeshLodError):
            compile_original_mesh_lod_set(self.base, reseal(altered))

    def test_truncated_or_tampered_binary_fails_even_with_new_archive_sha(self):
        built = self.render()
        glbs = {v["metadata"]["asset_id"]: v["glb"] for v in built["levels"]}
        bad = dict(glbs)
        key = next(iter(bad))
        bad[key] = bad[key][:-12]
        with self.assertRaises(OriginalMeshLodError):
            verify_original_mesh_lod_set(
                self.base, self.author, built["manifest"], bad,
            )

    def test_forged_distance_receipt_cannot_hide_source_change(self):
        built = self.render()
        fake = deepcopy(built["manifest"])
        fake["levels"][0]["switch_distance_mm"] = 5000
        fake["receipt_sha256"] = digest({
            k: v for k, v in fake.items() if k != "receipt_sha256"
        })
        with self.assertRaises(OriginalMeshLodError):
            verify_original_mesh_lod_set(
                self.base, self.author, fake,
                {v["metadata"]["asset_id"]: v["glb"]
                 for v in built["levels"]},
            )

    def test_resealing_original_source_revision_changes_lod_identity(self):
        before = self.render()
        changed = deepcopy(self.base)
        changed["document"]["size_mm"][0] += 100
        reseal(changed)
        after = compile_original_mesh_lod_set(changed, self.author)
        self.assertNotEqual(
            before["manifest"]["base_glb_sha256"],
            after["manifest"]["base_glb_sha256"],
        )
        self.assertNotEqual(
            before["manifest"]["levels"][0]["derived_record_sha256"],
            after["manifest"]["levels"][0]["derived_record_sha256"],
        )

    def test_duplicate_sets_on_single_base_are_denied(self):
        another = deepcopy(self.author)
        another["record_id"] = "other-author"
        reseal(another)
        with self.assertRaises(OriginalMeshLodError):
            compile_original_mesh_lod_collection({
                "trial-model-source": self.base,
                "trial-mesh-lods": self.author,
                "other-author": another,
            })

    def test_manifest_declares_no_native_execution(self):
        output = self.render()
        self.assertTrue(output["manifest"]["derived_from_reviewed_parametric_sources"])
        self.assertFalse(output["manifest"]["native_import_executed"])
        self.assertFalse(output["manifest"]["runtime_lod_switching_observed"])


class LodDescriptorCatalogTests(unittest.TestCase):
    def setUp(self):
        self.original = source_mesh()
        self.author = lod_record()
        self.lods = compile_original_mesh_lod_set(self.original, self.author)

    def catalog(self):
        from skeleton.jeeves.ai.studio_asset_descriptors import compile_asset_catalog
        return compile_asset_catalog(
            project_id="original-game", source_head_sha256="a" * 64,
            records={}, meshes=[self.lods["base"]], lod_sets=[self.lods],
        )

    def test_all_lod_glbs_have_searchable_descriptors_and_source_links(self):
        from skeleton.jeeves.ai.studio_asset_descriptors import (
            search_asset_catalog,
        )
        catalog = self.catalog()
        self.assertEqual(catalog["descriptor_count"], 3)
        levels = [
            asset for asset in catalog["descriptors"]
            if asset["metrics"].get("lod") is not None
        ]
        self.assertEqual(len(levels), 2)
        self.assertEqual(
            [asset["metrics"]["lod"]["switch_distance_mm"]
             for asset in levels], [8000, 22000],
        )
        for level in levels:
            self.assertEqual(level["metrics"]["lod"]["parent_asset_id"],
                             "trial-mesh")
            self.assertEqual(level["semantic_evidence"]["status"],
                             "inherited_parent_source_not_independent_vision")
            self.assertFalse(level["rights"]["legally_cleared_by_compiler"])
        results = search_asset_catalog(catalog, "lod2")
        self.assertEqual(results["results"][0]["asset_id"], "trial-mesh-lod2")

    def test_published_descriptors_replay_against_real_lod_binary_bytes(self):
        from skeleton.jeeves.ai.studio_asset_descriptors import (
            verify_asset_catalog, catalog_bytes,
        )
        catalog = self.catalog()
        verified = verify_asset_catalog(
            catalog_bytes(catalog), project_id="original-game",
            source_head_sha256="a" * 64,
            meshes=[self.lods["base"]], lod_sets=[self.lods],
        )
        self.assertEqual(verified["descriptor_count"], 3)

    def test_catalog_refuses_forged_lod_source_geometry(self):
        from skeleton.jeeves.ai.studio_asset_descriptors import (
            AssetDescriptorError, compile_asset_catalog,
        )
        swapped = deepcopy(self.lods)
        swapped["levels"][0]["glb"] = swapped["levels"][1]["glb"]
        with self.assertRaises(AssetDescriptorError):
            compile_asset_catalog(
                project_id="original-game", source_head_sha256="a" * 64,
                records={}, meshes=[swapped["base"]], lod_sets=[swapped],
            )

    def test_descriptor_inheritance_never_certifies_parent_semantics(self):
        catalog = self.catalog()
        base = next(item for item in catalog["descriptors"]
                    if item["asset_id"] == "trial-mesh")
        variants = [item for item in catalog["descriptors"]
                    if item["asset_id"].startswith("trial-mesh-lod")]
        self.assertEqual(base["semantic_evidence"]["status"], "structural_only")
        for variant in variants:
            self.assertIsNone(variant["semantic_evidence"]["source_record_id"])
            self.assertFalse(
                variant["semantic_evidence"]["scene_content_recognized_by_model"]
            )


class GodotMeshLodSceneTests(unittest.TestCase):
    def setUp(self):
        self.output = compile_original_mesh_lod_set(source_mesh(), lod_record())
        self.meta = self.output["base"]["metadata"]
        self.manifest = self.output["manifest"]

    def test_original_glb_has_importable_packed_scene_wrapper(self):
        resources = compile_mesh_godot_resources(self.meta)
        text = resources["game/frontier/meshes/trial-mesh.tscn"]
        self.assertIn('type="PackedScene"', text)
        self.assertIn("res://game/frontier/meshes/trial-mesh.glb", text)
        self.assertNotIn("lod.gd", text)

    def test_authored_lod_scene_has_hysteretic_camera_distance_switching(self):
        resources = compile_mesh_godot_resources(
            self.meta, lod_manifest=self.manifest,
        )
        gd = resources["game/frontier/meshes/trial-mesh.lod.gd"]
        self.assertIn("ORIGINAL_SWITCH_METERS", gd)
        self.assertIn("8.000", gd)
        self.assertIn("22.000", gd)
        self.assertIn("distance_to(global_position)", gd)
        self.assertIn("+ 0.25", gd)
        self.assertIn("- 0.25", gd)
        self.assertIn(".lod2.glb", gd)
        self.assertIn("queue_free()", gd)
        self.assertIn("PackedScene", gd)
        self.assertIn("res://game/frontier/meshes/trial-mesh.lod.gd",
                      resources["game/frontier/meshes/trial-mesh.lod.tscn"])

    def test_engine_source_exactly_replays_generated_scripts(self):
        resources = compile_mesh_godot_resources(
            self.meta, lod_manifest=self.manifest,
        )
        receipt = verify_mesh_godot_resources(
            self.meta, resources, lod_manifest=self.manifest,
        )
        self.assertEqual(receipt["lod_levels"], 2)
        self.assertFalse(receipt["engine_scene_instantiated"])
        self.assertTrue(receipt["source_text_reproducible"])

    def test_reject_substituted_runtime_lod_script(self):
        resources = compile_mesh_godot_resources(
            self.meta, lod_manifest=self.manifest,
        )
        fake = dict(resources)
        key = "game/frontier/meshes/trial-mesh.lod.gd"
        fake[key] = fake[key].replace(
            "distance_to(global_position)", "distance_to(Vector3.ZERO)",
        )
        with self.assertRaises(OriginalMeshGodotError):
            verify_mesh_godot_resources(
                self.meta, fake, lod_manifest=self.manifest,
            )

    def test_reject_missing_lod_scene(self):
        resources = compile_mesh_godot_resources(
            self.meta, lod_manifest=self.manifest,
        )
        resources.pop("game/frontier/meshes/trial-mesh.lod.tscn")
        with self.assertRaises(OriginalMeshGodotError):
            verify_mesh_godot_resources(
                self.meta, resources, lod_manifest=self.manifest,
            )

    def test_forged_model_receipt_refused_by_scene_generator(self):
        fake = deepcopy(self.meta)
        fake["glb_sha256"] = "0" * 64
        with self.assertRaises(OriginalMeshGodotError):
            compile_mesh_godot_resources(fake)


class SourceStoreLodMutationTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        export_root = root / "exports"
        export_root.mkdir()
        self.store = CreatorProjectSourceStore(
            root / "assets.sqlite", project_id="original-game",
            export_root=export_root,
        )
        self.addCleanup(self.store.close)

    def create(self, rec):
        return self.store.create(build_creator_command(
            "create", project_id="original-game",
            payload={"intent": {
                "record_id": rec["record_id"], "facet": rec["facet"],
                "document": rec["document"], "depends_on": rec["depends_on"],
            }},
        ))

    def test_authored_lod_create_is_persisted_after_source_validation(self):
        self.create(source_mesh())
        self.create(lod_record())
        self.assertEqual(self.store.snapshot()["source_count"], 2)
        self.assertEqual(compile_original_mesh_lod_collection(
            self.store._records,
        )["count"], 1)

    def test_invalid_lod_does_not_write_source_history(self):
        self.create(source_mesh())
        invalid = lod_record()
        invalid["document"]["levels"][0]["segments"] = 999
        with self.assertRaises(OriginalMeshLodError):
            self.create(invalid)
        self.assertEqual(self.store.snapshot()["source_count"], 1)

    def test_source_store_exposes_all_reviewed_lod_descriptors_to_jeeves(self):
        self.create(source_mesh())
        self.create(lod_record())
        report = self.store.search_original_assets(
            "trial-mesh-lod2", kind="procedural_mesh",
        )
        self.assertEqual(report["asset_count"], 3)
        self.assertEqual(report["results"][0]["asset_id"], "trial-mesh-lod2")
        self.assertEqual(report["results"][0]["metrics"]["lod"]["level"], 2)

    def test_updating_original_mesh_cannot_invalidate_existing_lods(self):
        self.create(source_mesh())
        self.create(lod_record())
        old = self.store._records["trial-model-source"]
        with self.assertRaises(OriginalMeshLodError):
            self.store.edit(build_creator_command(
                "edit", project_id="original-game",
                payload={
                    "target_id": "trial-model-source", "expected_revision": 1,
                    "patch": {"set": {"primitive": "box"}, "remove": []},
                },
            ))
        self.assertEqual(self.store.snapshot()["source_count"], 2)
        self.assertEqual(self.store._records["trial-model-source"]["source_sha256"],
                         old["source_sha256"])


if __name__ == "__main__":
    unittest.main()
