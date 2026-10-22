"""Original game world chunk and resource load-planner regression suite.

This validates the actual authored 3D assets and scene bounds from the
existing asset compilers. Planned load/unload resources are never claimed
to have been streamed, imported or physically simulated in Godot.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_creator_source import CreatorProjectSourceStore
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_world_chunks import (
    WorldChunkError, compile_world_chunk_catalog, plan_chunk_resources,
    verify_world_chunk_catalog, world_chunk_catalog_bytes,
)
from skeleton.jeeves.ai.studio_world_spatial_index import (
    compile_world_spatial_index,
)
from skeleton.testing.test_jeeves_studio_world_spatial_index_2026 import (
    authored_world,
)
from skeleton.testing.test_jeeves_studio_asset_compilers_2026 import (
    mesh_record,
)
from skeleton.testing.test_jeeves_studio_mesh_placements_2026 import (
    instance_record,
)


def setup_world(*, physical: bool = False, lod: bool = False) -> tuple:
    asset_catalog, scene, _ = authored_world(physical=physical, lod=lod)
    source = compile_world_spatial_index(
        project_id="world-game", source_head_sha256="a" * 64,
        catalog=asset_catalog, placements=scene,
    )
    chunks = compile_world_chunk_catalog(source)
    return source, chunks


class WorldChunkCompilerTests(unittest.TestCase):
    def test_real_scene_produces_compact_byte_exact_home_cell_catalog(self):
        spatial, chunks = setup_world()
        self.assertEqual(chunks["total_instances"], 1)
        self.assertEqual(chunks["chunk_count"], 1)
        self.assertEqual(chunks["chunks"][0]["cell"], "0,0,-1")
        self.assertEqual(chunks["chunks"][0]["instance_ids"], ["temple-doorway"])
        self.assertEqual(chunks["chunk_edge_mm"], 64_000)
        self.assertEqual(
            chunks["source_world_receipt_sha256"], spatial["receipt_sha256"],
        )
        self.assertFalse(chunks["native_chunk_streaming_observed"])
        self.assertEqual(chunks, compile_world_chunk_catalog(spatial))

    def test_source_catalog_replays_exact_published_bytes(self):
        world, catalog = setup_world()
        checked = verify_world_chunk_catalog(
            world_chunk_catalog_bytes(catalog), source_index=world,
        )
        self.assertEqual(checked["original_instances_replayed"], 1)
        self.assertEqual(checked["home_cells_replayed"], 1)
        self.assertTrue(checked["chunk_membership_reproduced"])
        self.assertFalse(checked["godot_streaming_executed"])

    def test_camera_near_original_asset_proposes_real_instantiable_scene(self):
        spatial, chunks = setup_world()
        planned = plan_chunk_resources(
            chunks, spatial, camera_mm=[1500, 3200, -550],
            view_radius_mm=0,
        )
        self.assertEqual(planned["candidate_instances_in_view"], 1)
        self.assertEqual(planned["selected_instances"], ["temple-doorway"])
        self.assertEqual(planned["resources_to_load"], [
            "game/frontier/meshes/trial-mesh.tscn",
        ])
        self.assertEqual(planned["resources_to_release"], [])
        self.assertFalse(planned["actual_resources_loaded"])

    def test_existing_same_asset_load_is_not_reloaded(self):
        spatial, chunks = setup_world()
        file = "game/frontier/meshes/trial-mesh.tscn"
        planned = plan_chunk_resources(
            chunks, spatial, camera_mm=[1500, 3200, -550],
            view_radius_mm=0, previously_loaded=[file],
        )
        self.assertEqual(planned["resources_to_load"], [])
        self.assertEqual(planned["resources_to_release"], [])
        self.assertEqual(planned["required_scene_resources"], [file])

    def test_far_camera_releases_no_longer_needed_asset(self):
        spatial, chunks = setup_world()
        file = "game/frontier/meshes/trial-mesh.tscn"
        planned = plan_chunk_resources(
            chunks, spatial, camera_mm=[9_000_000, 0, 9_000_000],
            view_radius_mm=0, previously_loaded=[file],
        )
        self.assertEqual(planned["selected_instances"], [])
        self.assertEqual(planned["resources_to_release"], [file])
        self.assertEqual(planned["resources_to_load"], [])

    def test_negative_cell_boundary_does_not_lose_asset(self):
        spatial, chunks = setup_world()
        self.assertEqual(chunks["chunks"][0]["cell"], "0,0,-1")
        cam = spatial["instances"][0]["position_mm"]
        planned = plan_chunk_resources(
            chunks, spatial, camera_mm=cam, view_radius_mm=0,
        )
        self.assertEqual(planned["candidate_instances_in_view"], 1)

    def test_truncated_camera_budget_does_not_unload_other_visible_asset(self):
        world, _ = setup_world()
        second = deepcopy(world["instances"][0])
        second["instance_id"] = "farther-visible"
        second["asset_id"] = "other-reviewed-mesh"
        second["scene_resource_path"] = (
            "game/frontier/meshes/other-reviewed-mesh.tscn"
        )
        second["position_mm"][0] += 5000
        second["broadphase_aabb_min_mm"][0] += 5000
        second["broadphase_aabb_max_mm"][0] += 5000
        second["receipt_sha256"] = digest({
            k: v for k, v in second.items() if k != "receipt_sha256"
        })
        world["instances"].append(second)
        world["instance_count"] = 2
        world["receipt_sha256"] = digest({
            k: v for k, v in world.items() if k != "receipt_sha256"
        })
        chunks = compile_world_chunk_catalog(world)
        already_loaded = second["scene_resource_path"]
        plan = plan_chunk_resources(
            chunks, world, camera_mm=[1500, 3200, -550],
            view_radius_mm=10000,
            previously_loaded=[already_loaded], limit=1,
        )
        self.assertTrue(plan["selection_truncated"])
        self.assertEqual(plan["candidate_instances_in_view"], 2)
        self.assertEqual(plan["selected_instances"], ["temple-doorway"])
        self.assertEqual(plan["resources_to_release"], [])
        self.assertEqual(plan["resources_to_load"], [
            "game/frontier/meshes/trial-mesh.tscn",
        ])

    def test_source_glb_with_lod_selects_importable_lod_scene(self):
        spatial, chunks = setup_world(lod=True)
        plan = plan_chunk_resources(
            chunks, spatial, camera_mm=[1500, 3200, -550],
            view_radius_mm=1000,
        )
        self.assertEqual(plan["resources_to_load"], [
            "game/frontier/meshes/trial-mesh.lod.tscn",
        ])
        self.assertFalse(plan["actual_native_gpu_residency_observed"])

    def test_physics_world_selects_actual_compiled_body_resource(self):
        spatial, chunks = setup_world(physical=True)
        plan = plan_chunk_resources(
            chunks, spatial, camera_mm=[1500, 3200, -550],
            view_radius_mm=1,
        )
        self.assertEqual(plan["resources_to_load"], [
            "game/frontier/meshes/trial-mesh.physics.tscn",
        ])
        self.assertEqual(plan["selected_instances"], ["temple-doorway"])

    def test_chunk_index_denies_rehashed_false_membership(self):
        spatial, chunks = setup_world()
        fake = deepcopy(chunks)
        fake["chunks"][0]["instance_ids"] = ["made-up-scene"]
        fake["receipt_sha256"] = digest({
            k: v for k, v in fake.items() if k != "receipt_sha256"
        })
        with self.assertRaises(WorldChunkError):
            verify_world_chunk_catalog(
                world_chunk_catalog_bytes(fake), source_index=spatial,
            )
        with self.assertRaises(WorldChunkError):
            plan_chunk_resources(
                fake, spatial, camera_mm=[1500, 3200, -550],
                view_radius_mm=0,
            )

    def test_chunk_planner_denies_foreign_old_resources(self):
        spatial, chunks = setup_world()
        for bad in (
            "../rogue.tscn",
            "res://injected.gd",
            "game/frontier/meshes/trial-mesh.gd",
            "game/frontier/meshes/../evil.tscn",
        ):
            with self.subTest(asset=bad):
                with self.assertRaises(WorldChunkError):
                    plan_chunk_resources(
                        chunks, spatial, camera_mm=[0, 0, 0],
                        view_radius_mm=1000, previously_loaded=[bad],
                    )

    def test_camera_query_refuses_boolean_and_unbounded_limits(self):
        spatial, chunks = setup_world()
        for distance in (True, -1, 10_000_001):
            with self.assertRaises(WorldChunkError):
                plan_chunk_resources(
                    chunks, spatial, camera_mm=[0, 0, 0],
                    view_radius_mm=distance,
                )
        with self.assertRaises(WorldChunkError):
            plan_chunk_resources(
                chunks, spatial, camera_mm=[0, 0, 0],
                view_radius_mm=1, limit=1000,
            )

    def test_forged_placement_radius_refused_at_chunk_compilation(self):
        spatial, _ = setup_world()
        forged = deepcopy(spatial)
        forged["instances"][0]["broadphase_aabb_max_mm"][0] -= 100
        forged["instances"][0]["receipt_sha256"] = digest({
            k: v for k, v in forged["instances"][0].items()
            if k != "receipt_sha256"
        })
        forged["receipt_sha256"] = digest({
            k: v for k, v in forged.items() if k != "receipt_sha256"
        })
        with self.assertRaises(WorldChunkError):
            compile_world_chunk_catalog(forged)

    def test_load_plan_is_reproducibly_content_sealed(self):
        world, chunks = setup_world()
        plan = plan_chunk_resources(
            chunks, world, camera_mm=[1500, 3200, -550],
            view_radius_mm=10_000,
        )
        self.assertEqual(plan["receipt_sha256"], digest({
            k: v for k, v in plan.items() if k != "receipt_sha256"
        }))
        self.assertEqual(plan, plan_chunk_resources(
            chunks, world, camera_mm=[1500, 3200, -550],
            view_radius_mm=10_000,
        ))

    def test_unplaced_world_has_empty_chunk_index_and_no_forged_loads(self):
        from skeleton.jeeves.ai.studio_asset_descriptors import compile_asset_catalog
        from skeleton.jeeves.ai.studio_original_mesh import compile_original_mesh
        from skeleton.jeeves.ai.studio_original_mesh_placements import compile_original_mesh_placements
        base = mesh_record()
        catalog = compile_asset_catalog(
            project_id="world-game", source_head_sha256="a" * 64,
            records={}, meshes=[compile_original_mesh(base)],
        )
        placements = compile_original_mesh_placements({})
        source = compile_world_spatial_index(
            project_id="world-game", source_head_sha256="a" * 64,
            catalog=catalog, placements=placements["metadata"],
        )
        chunks = compile_world_chunk_catalog(source)
        self.assertEqual(chunks["chunk_count"], 0)
        self.assertEqual(plan_chunk_resources(
            chunks, source, camera_mm=[0, 0, 0],
            view_radius_mm=10000,
        )["required_scene_resources"], [])


class ChunkProjectOwnerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        (base / "out").mkdir()
        self.owner = CreatorProjectSourceStore(
            base / "store.sqlite", project_id="world-game",
            export_root=base / "out",
        )
        self.addCleanup(self.owner.close)

    def create(self, record):
        self.owner.create(build_creator_command(
            "create", project_id="world-game",
            payload={"intent": {
                "record_id": record["record_id"],
                "facet": record["facet"],
                "document": record["document"],
                "depends_on": record["depends_on"],
            }},
        ))

    def test_real_sqlite_owner_emits_queryable_source_chunk_catalog(self):
        self.create(mesh_record())
        self.create(instance_record())
        chunk = self.owner.compiled_world_chunk_catalog()
        self.assertEqual(chunk["chunk_count"], 1)
        plan = self.owner.plan_world_scene_resources(
            camera_mm=[1500, 3200, -550], view_radius_mm=0,
        )
        self.assertEqual(plan["project_id"], "world-game")
        self.assertEqual(plan["source_head_sha256"], self.owner.head_identity())
        self.assertEqual(plan["resources_to_load"], [
            "game/frontier/meshes/trial-mesh.tscn",
        ])
        self.assertEqual(len(plan["resource_planning_receipt_sha256"]), 64)

    def test_source_owner_refuses_stale_scene_after_revision_edit(self):
        self.create(mesh_record())
        self.create(instance_record())
        one = self.owner.compiled_world_chunk_catalog()
        self.owner.edit(build_creator_command(
            "edit", project_id="world-game",
            payload={
                "target_id": "original-scene-placement",
                "expected_revision": 1,
                "patch": {
                    "set": {"position_mm": [-95000, 5000, 70000]},
                    "remove": [],
                },
            },
        ))
        two = self.owner.compiled_world_chunk_catalog()
        self.assertNotEqual(one["source_world_index_sha256"],
                            two["source_world_index_sha256"])
        self.assertNotEqual(one["chunks"][0]["cell"],
                            two["chunks"][0]["cell"])


if __name__ == "__main__":
    unittest.main()
