"""Real scene world-space asset descriptors and 3D queries, with tamper tests."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
import zipfile

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_asset_descriptors import compile_asset_catalog
from skeleton.jeeves.ai.studio_creator_source import CreatorProjectSourceStore
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_original_mesh import compile_original_mesh
from skeleton.jeeves.ai.studio_original_mesh_lod import compile_original_mesh_lod_set
from skeleton.jeeves.ai.studio_original_mesh_physics import compile_original_mesh_physics
from skeleton.jeeves.ai.studio_original_mesh_placements import (
    compile_original_mesh_placements,
)
from skeleton.jeeves.ai.studio_world_spatial_index import (
    WorldSpatialIndexError, compile_world_spatial_index,
    query_world_spatial_index, spatial_index_bytes,
    verify_world_spatial_index,
)
from skeleton.testing.test_jeeves_studio_asset_compilers_2026 import (
    mesh_record, reseal,
)
from skeleton.testing.test_jeeves_studio_mesh_lod_2026 import (
    source_mesh, lod_record,
)
from skeleton.testing.test_jeeves_studio_mesh_physics_2026 import source_body
from skeleton.testing.test_jeeves_studio_mesh_placements_2026 import instance_record


def authored_world(*, physical: bool = False, lod: bool = False) -> tuple:
    original = source_mesh() if lod else mesh_record()
    place = instance_record(phys=physical)
    sources = {original["record_id"]: original, place["record_id"]: place}
    mesh = compile_original_mesh(original)
    lods = []
    physical_sources = []
    if lod:
        authored_lod = lod_record()
        sources[authored_lod["record_id"]] = authored_lod
        lods = [compile_original_mesh_lod_set(original, authored_lod)]
    if physical:
        body = source_body()
        sources[body["record_id"]] = body
        compiled = compile_original_mesh_physics(
            original, body, has_lod=lod,
        )
        physical_sources = [{
            "base_record": original, "source_record": body, **compiled,
        }]
    catalog = compile_asset_catalog(
        project_id="world-game", source_head_sha256="a" * 64,
        records=sources, meshes=[mesh], lod_sets=lods,
        physics_assets=physical_sources,
    )
    placements = compile_original_mesh_placements(
        sources,
        lod_assets=frozenset({"trial-mesh"} if lod else []),
        physics_assets=frozenset({"trial-mesh"} if physical else []),
    )
    return catalog, placements["metadata"], sources


class WorldIndexCompilerTests(unittest.TestCase):
    def scene(self, *, physical=False, lod=False):
        c, p, _ = authored_world(physical=physical, lod=lod)
        return compile_world_spatial_index(
            project_id="world-game", source_head_sha256="a" * 64,
            catalog=c, placements=p,
        )

    def test_actual_3d_instance_has_source_owned_searchable_bounds(self):
        result = self.scene()
        self.assertEqual(result["instance_count"], 1)
        item = result["instances"][0]
        self.assertEqual(item["instance_id"], "temple-doorway")
        self.assertEqual(item["asset_id"], "trial-mesh")
        self.assertEqual(item["position_mm"], [1500, 3200, -550])
        self.assertEqual(item["rotation_deg"], [0, 90, 0])
        self.assertEqual(item["scale_per_mille"], 1200)
        self.assertEqual(item["kind"], "visual")
        self.assertIsNone(item["physics_body_type"])
        self.assertGreater(item["conservative_radius_mm"], 0)
        self.assertEqual(item["broadphase_aabb_min_mm"], [
            item["position_mm"][i] - item["conservative_radius_mm"]
            for i in range(3)
        ])
        self.assertFalse(result["actual_native_scene_import_observed"])

    def test_index_source_has_portable_complete_sha(self):
        index = self.scene()
        self.assertEqual(index["receipt_sha256"], digest({
            k: v for k, v in index.items() if k != "receipt_sha256"
        }))
        self.assertEqual(
            spatial_index_bytes(index), spatial_index_bytes(self.scene()),
        )

    def test_binary_replay_rebuilds_all_scene_and_mesh_ancestry(self):
        catalog, placements, _ = authored_world()
        result = compile_world_spatial_index(
            project_id="world-game", source_head_sha256="a" * 64,
            catalog=catalog, placements=placements,
        )
        proof = verify_world_spatial_index(
            spatial_index_bytes(result), project_id="world-game",
            source_head_sha256="a" * 64,
            catalog=catalog, placements=placements,
        )
        self.assertEqual(proof["scene_instances_replayed"], 1)
        self.assertTrue(proof["source_scene_and_binary_asset_receipts_replayed"])
        self.assertFalse(proof["native_3d_scene_visibility_observed"])

    def test_query_culls_far_away_world_instances(self):
        index = self.scene()
        near = query_world_spatial_index(
            index, center_mm=[1500, 3200, -550], radius_mm=0,
        )
        self.assertEqual(near["matches"], 1)
        distant = query_world_spatial_index(
            index, center_mm=[9000000, 9000000, 9000000],
            radius_mm=10,
        )
        self.assertEqual(distant["matches"], 0)

    def test_query_uses_conservative_bounds_for_nearby_objects(self):
        index = self.scene()
        source = index["instances"][0]
        result = query_world_spatial_index(
            index, center_mm=[
                source["position_mm"][0] + source["conservative_radius_mm"],
                source["position_mm"][1],
                source["position_mm"][2],
            ], radius_mm=0,
        )
        self.assertEqual(result["matches"], 1)
        self.assertFalse(result["native_collision_or_visibility_verified"])

    def test_search_body_filter_is_source_governed(self):
        index = self.scene(physical=True)
        item = index["instances"][0]
        self.assertEqual(item["kind"], "physics")
        self.assertEqual(item["physics_body_type"], "static")
        result = query_world_spatial_index(
            index, center_mm=item["position_mm"], radius_mm=0,
            kind="physics",
        )
        self.assertEqual(result["matches"], 1)
        self.assertEqual(query_world_spatial_index(
            index, center_mm=item["position_mm"], radius_mm=0,
            kind="visual",
        )["matches"], 0)

    def test_source_derived_lod_is_described_without_claiming_engine_import(self):
        index = self.scene(lod=True)
        item = index["instances"][0]
        self.assertTrue(item["authored_lod_available"])
        self.assertEqual(item["kind"], "lod")
        self.assertIn("trial-mesh.lod.tscn", item["scene_resource_path"])

    def test_replay_rejects_changed_scene_position_with_resigned_index(self):
        catalog, source, _ = authored_world()
        original = compile_world_spatial_index(
            project_id="world-game", source_head_sha256="a" * 64,
            catalog=catalog, placements=source,
        )
        tampered = deepcopy(original)
        tampered["instances"][0]["position_mm"][0] += 10000
        tampered["receipt_sha256"] = digest({
            k: v for k, v in tampered.items() if k != "receipt_sha256"
        })
        with self.assertRaises(WorldSpatialIndexError):
            verify_world_spatial_index(
                spatial_index_bytes(tampered), project_id="world-game",
                source_head_sha256="a" * 64, catalog=catalog, placements=source,
            )

    def test_spatial_compiler_rejects_forged_asset_catalog_parent_hash(self):
        catalog, placements, _ = authored_world()
        fake = deepcopy(catalog)
        fake["descriptors"][0]["content_sha256"] = "f" * 64
        with self.assertRaises(WorldSpatialIndexError):
            compile_world_spatial_index(
                project_id="world-game", source_head_sha256="a" * 64,
                catalog=fake, placements=placements,
            )

    def test_spatial_compiler_rejects_source_wrong_asset_id(self):
        catalog, placements, _ = authored_world()
        bad = deepcopy(placements)
        bad["instances"][0]["asset_id"] = "unreviewed-object"
        bad["receipt_sha256"] = digest({
            k: v for k, v in bad.items() if k != "receipt_sha256"
        })
        with self.assertRaises(WorldSpatialIndexError):
            compile_world_spatial_index(
                project_id="world-game", source_head_sha256="a" * 64,
                catalog=catalog, placements=bad,
            )

    def test_spatial_queries_reject_boolean_or_oversized_radius(self):
        index = self.scene()
        for radius in (True, -1, 10_000_001):
            with self.assertRaises(WorldSpatialIndexError):
                query_world_spatial_index(
                    index, center_mm=[0, 0, 0], radius_mm=radius,
                )

    def test_spatial_queries_reject_unverified_mutated_receipts(self):
        bad = self.scene()
        bad["instances"][0]["position_mm"] = [0, 0, 0]
        with self.assertRaises(WorldSpatialIndexError):
            query_world_spatial_index(
                bad, center_mm=[0, 0, 0], radius_mm=1000,
            )

    def test_empty_world_has_real_empty_index_not_placeholder_instances(self):
        base = mesh_record()
        catalog = compile_asset_catalog(
            project_id="world-game", source_head_sha256="a" * 64,
            records={}, meshes=[compile_original_mesh(base)],
        )
        placements = compile_original_mesh_placements({})
        result = compile_world_spatial_index(
            project_id="world-game", source_head_sha256="a" * 64,
            catalog=catalog, placements=placements["metadata"],
        )
        self.assertEqual(result["instance_count"], 0)
        self.assertEqual(result["instances"], [])


class OriginalSpatialStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        exports = root / "exports"
        exports.mkdir()
        self.store = CreatorProjectSourceStore(
            root / "world.sqlite", project_id="world-game",
            export_root=exports,
        )
        self.addCleanup(self.store.close)

    def add(self, source):
        self.store.create(build_creator_command(
            "create", project_id="world-game",
            payload={"intent": {
                "record_id": source["record_id"], "facet": source["facet"],
                "document": source["document"],
                "depends_on": source["depends_on"],
            }},
        ))

    def test_authored_instance_is_available_to_native_jeeves_spatial_retrieval(self):
        self.add(mesh_record())
        self.add(instance_record())
        result = self.store.search_world_instances(
            center_mm=[1500, 3200, -550], radius_mm=0,
        )
        self.assertEqual(result["matches"], 1)
        self.assertEqual(result["instances"][0]["instance_id"], "temple-doorway")
        self.assertEqual(result["source_head_sha256"], self.store.head_identity())
        self.assertEqual(len(result["retrieval_receipt_sha256"]), 64)

    def test_spatial_store_reflects_real_source_revision_not_stale_cache(self):
        self.add(mesh_record())
        self.add(instance_record())
        first = self.store.compiled_world_spatial_index()
        self.store.edit(build_creator_command(
            "edit", project_id="world-game",
            payload={
                "target_id": "original-scene-placement",
                "expected_revision": 1,
                "patch": {"set": {"position_mm": [3000, 1000, 3000]},
                          "remove": []},
            },
        ))
        next_index = self.store.compiled_world_spatial_index()
        self.assertNotEqual(first["source_head_sha256"],
                            next_index["source_head_sha256"])
        self.assertEqual(next_index["instances"][0]["position_mm"],
                         [3000, 1000, 3000])


if __name__ == "__main__":
    unittest.main()
