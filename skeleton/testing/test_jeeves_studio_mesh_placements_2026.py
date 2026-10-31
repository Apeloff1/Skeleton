"""Adversarial reviewed original 3D scene placement and Godot root proof."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_creator_source import CreatorProjectSourceStore
from skeleton.jeeves.ai.studio_original_mesh_placements import (
    OriginalMeshPlacementError,
    PLACEMENT_SCENE,
    attach_authored_meshes_to_expedition,
    compile_original_mesh_placements,
    compile_original_mesh_placement_source_bundle,
    verify_original_mesh_placement_source_bundle,
)
from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCENE
from skeleton.testing.test_jeeves_studio_asset_compilers_2026 import (
    mesh_record, reseal,
)
from skeleton.testing.test_jeeves_studio_mesh_lod_2026 import (
    source_mesh, lod_record,
)
from skeleton.testing.test_jeeves_studio_mesh_physics_2026 import source_body


def instance_record(*, phys: bool = False) -> dict:
    dependencies = ["trial-model-source"]
    physics_id = None
    if phys:
        physics_id = "my-original-physics"
        dependencies.append(physics_id)
    return reseal({
        "record_id": "original-scene-placement", "facet": "scene_forge",
        "revision": 1, "depends_on": dependencies,
        "document": {
            "kind": "original_mesh_instance",
            "instance_id": "temple-doorway",
            "base_record_id": "trial-model-source",
            "asset_id": "trial-mesh",
            "physics_record_id": physics_id,
            "position_mm": [1500, 3200, -550],
            "rotation_deg": [0, 90, 0],
            "scale_per_mille": 1200,
        },
    })


class OriginalMeshScenePlacementTests(unittest.TestCase):
    def setUp(self):
        self.base = mesh_record()
        self.visual = instance_record()

    def sources(self):
        return {
            self.base["record_id"]: self.base,
            self.visual["record_id"]: self.visual,
        }

    def test_actual_mesh_instance_writes_typed_godot_scene(self):
        built = compile_original_mesh_placements(self.sources())
        scene = built["files"][PLACEMENT_SCENE]
        self.assertIn('type="PackedScene"', scene)
        self.assertIn("res://game/frontier/meshes/trial-mesh.tscn", scene)
        self.assertIn("temple-doorway", scene)
        self.assertIn("position = Vector3(1.5000, 3.2000, -0.5500)", scene)
        self.assertIn("rotation_degrees = Vector3(0.0000, 90.0000, 0.0000)", scene)
        self.assertIn("scale = Vector3(1.2000, 1.2000, 1.2000)", scene)
        self.assertEqual(
            built["metadata"]["placement_scene_sha256"],
            sha256(scene.encode("utf-8")).hexdigest(),
        )

    def test_real_game_expedition_instantiates_authored_mesh_child(self):
        built = compile_original_mesh_placements(self.sources())
        root = attach_authored_meshes_to_expedition(_GODOT_SCENE, built)
        self.assertIn('[gd_scene load_steps=3 format=3]', root)
        self.assertIn("res://game/frontier/mesh_placements.tscn", root)
        self.assertIn('name="OriginalMeshInstances"', root)
        self.assertIn('instance=ExtResource("OriginalMeshes")', root)
        self.assertIn('script = ExtResource("1")', root)

    def test_full_approved_source_bundle_reconstructs_real_scene_and_root(self):
        records = self.sources()
        compiled = compile_original_mesh_placements(records)
        bundle = compile_original_mesh_placement_source_bundle(records, compiled)
        root = attach_authored_meshes_to_expedition(_GODOT_SCENE, compiled)
        checked = verify_original_mesh_placement_source_bundle(
            bundle,
            published_scene=compiled["files"][PLACEMENT_SCENE],
            published_root=root,
            expected_lod_asset_ids=frozenset(),
            expected_physics_asset_ids=frozenset(),
        )
        self.assertTrue(checked["actual_3d_assets_instanced_in_source_scene"])
        self.assertEqual(checked["instances_replayed"], 1)
        self.assertFalse(checked["native_engine_scene_import_verified"])

    def test_runtime_physics_placement_requires_real_approved_body(self):
        instance = instance_record(phys=True)
        records = {self.base["record_id"]: self.base,
                   instance["record_id"]: instance}
        with self.assertRaises(OriginalMeshPlacementError):
            compile_original_mesh_placements(
                records, physics_assets=frozenset({"trial-mesh"}),
            )
        physical = source_body()
        records[physical["record_id"]] = physical
        compiled = compile_original_mesh_placements(
            records, physics_assets=frozenset({"trial-mesh"}),
        )
        self.assertIn("trial-mesh.physics.tscn",
                      compiled["files"][PLACEMENT_SCENE])
        self.assertEqual(
            compiled["metadata"]["instances"][0]["visual_or_physics"],
            "physics",
        )

    def test_source_authorized_lod_scene_is_instanced_not_flattened(self):
        sources = self.sources()
        sources[lod_record()["record_id"]] = lod_record()
        compiled = compile_original_mesh_placements(
            sources, lod_assets=frozenset({"trial-mesh"}),
        )
        self.assertIn("trial-mesh.lod.tscn",
                      compiled["files"][PLACEMENT_SCENE])
        self.assertEqual(
            compiled["metadata"]["instances"][0]["visual_or_physics"], "lod",
        )

    def test_source_shown_in_game_requires_correct_parent_mesh_hash(self):
        records = self.sources()
        compiled = compile_original_mesh_placements(records)
        bundle = compile_original_mesh_placement_source_bundle(records, compiled)
        scene = compiled["files"][PLACEMENT_SCENE]
        root = attach_authored_meshes_to_expedition(_GODOT_SCENE, compiled)
        changed = scene.replace("trial-mesh.tscn", "other-mesh.tscn")
        with self.assertRaises(OriginalMeshPlacementError):
            verify_original_mesh_placement_source_bundle(
                bundle, published_scene=changed, published_root=root,
                expected_lod_asset_ids=frozenset(),
                expected_physics_asset_ids=frozenset(),
            )

    def test_unreviewed_root_replacement_is_rejected(self):
        compiled = compile_original_mesh_placements(self.sources())
        with self.assertRaises(OriginalMeshPlacementError):
            attach_authored_meshes_to_expedition(
                _GODOT_SCENE.replace("FrontierExpedition", "MaliciousRoot"),
                compiled,
            )

    def test_empty_placeholders_do_not_mutate_game_root(self):
        compiled = compile_original_mesh_placements({})
        self.assertEqual(compiled["metadata"]["instance_count"], 0)
        self.assertEqual(compiled["files"], {})
        self.assertEqual(
            attach_authored_meshes_to_expedition(_GODOT_SCENE, compiled),
            _GODOT_SCENE,
        )

    def test_rejects_foreign_physics_source_record(self):
        physical = source_body()
        bad = deepcopy(physical)
        bad["document"]["asset_id"] = "foreign-mesh"
        reseal(bad)
        sources = {
            "trial-model-source": self.base,
            "my-original-physics": bad,
            "original-scene-placement": instance_record(phys=True),
        }
        with self.assertRaises(OriginalMeshPlacementError):
            compile_original_mesh_placements(
                sources, physics_assets=frozenset({"trial-mesh"}),
            )

    def test_position_rotation_scale_reject_invalid_or_boolean_values(self):
        for field, value in (
            ("position_mm", [True, 0, 0]),
            ("rotation_deg", [0, 361, 0]),
            ("scale_per_mille", 0),
            ("scale_per_mille", True),
            ("position_mm", [0, 0]),
        ):
            with self.subTest(field=field):
                sample = deepcopy(self.visual)
                sample["document"][field] = value
                records = {
                    self.base["record_id"]: self.base,
                    sample["record_id"]: reseal(sample),
                }
                with self.assertRaises(OriginalMeshPlacementError):
                    compile_original_mesh_placements(records)

    def test_duplicate_instance_names_refused(self):
        second = deepcopy(self.visual)
        second["record_id"] = "another-scene-placement"
        reseal(second)
        with self.assertRaises(OriginalMeshPlacementError):
            compile_original_mesh_placements({
                "trial-model-source": self.base,
                "original-scene-placement": self.visual,
                "another-scene-placement": second,
            })

    def test_revised_source_receipt_changes_scene_provenance(self):
        before = compile_original_mesh_placements(self.sources())
        changed = deepcopy(self.visual)
        changed["revision"] = 2
        changed["document"]["position_mm"] = [3000, 3200, 0]
        reseal(changed)
        after = compile_original_mesh_placements({
            self.base["record_id"]: self.base,
            changed["record_id"]: changed,
        })
        self.assertNotEqual(before["metadata"]["receipt_sha256"],
                            after["metadata"]["receipt_sha256"])

    def test_forged_lod_source_claim_refused_during_package_replay(self):
        lod = lod_record()
        records = {
            "trial-model-source": source_mesh(),
            "original-scene-placement": self.visual,
            "trial-mesh-lods": lod,
        }
        compiled = compile_original_mesh_placements(
            records, lod_assets=frozenset({"trial-mesh"}),
        )
        bundle = compile_original_mesh_placement_source_bundle(records, compiled)
        root = attach_authored_meshes_to_expedition(_GODOT_SCENE, compiled)
        with self.assertRaises(OriginalMeshPlacementError):
            verify_original_mesh_placement_source_bundle(
                bundle, published_scene=compiled["files"][PLACEMENT_SCENE],
                published_root=root,
                expected_lod_asset_ids=frozenset(),
                expected_physics_asset_ids=frozenset(),
            )


class OriginalMeshSceneSourceStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        exports = root / "exports"
        exports.mkdir()
        self.store = CreatorProjectSourceStore(
            root / "world.sqlite", project_id="original-game",
            export_root=exports,
        )
        self.addCleanup(self.store.close)

    def create(self, source):
        return self.store.create(build_creator_command(
            "create", project_id="original-game",
            payload={"intent": {
                "record_id": source["record_id"], "facet": source["facet"],
                "document": source["document"], "depends_on": source["depends_on"],
            }},
        ))

    def test_original_mesh_scene_mutation_is_source_recorded(self):
        self.create(mesh_record())
        self.create(instance_record())
        self.assertEqual(self.store.snapshot()["source_count"], 2)

    def test_scene_cannot_reference_unapproved_or_missing_physics(self):
        self.create(mesh_record())
        with self.assertRaises(Exception):
            self.create(instance_record(phys=True))
        self.assertEqual(self.store.snapshot()["source_count"], 1)

    def test_mesh_rename_cannot_leave_orphan_placement(self):
        self.create(mesh_record())
        self.create(instance_record())
        with self.assertRaises(OriginalMeshPlacementError):
            self.store.edit(build_creator_command(
                "edit", project_id="original-game",
                payload={
                    "target_id": "trial-model-source",
                    "expected_revision": 1,
                    "patch": {"set": {"asset_id": "foreign-mesh"}, "remove": []},
                },
            ))


if __name__ == "__main__":
    unittest.main()
