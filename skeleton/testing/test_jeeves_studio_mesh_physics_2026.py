"""Source-authored original 3D Godot collision/physics compiler regressions."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_asset_descriptors import (
    AssetDescriptorError, compile_asset_catalog, catalog_bytes,
    search_asset_catalog, verify_asset_catalog,
)
from skeleton.jeeves.ai.studio_creator_source import (
    CreatorProjectSourceStore, CreatorSourceError,
)
from skeleton.jeeves.ai.studio_original_mesh import compile_original_mesh
from skeleton.jeeves.ai.studio_original_mesh_physics import (
    OriginalMeshPhysicsError, compile_original_mesh_physics,
    compile_original_mesh_physics_collection, verify_original_mesh_physics,
)
from skeleton.testing.test_jeeves_studio_asset_compilers_2026 import (
    mesh_record, reseal,
)
from skeleton.testing.test_jeeves_studio_mesh_lod_2026 import (
    lod_record, source_mesh,
)


def source_body(body_type: str = "static") -> dict:
    return reseal({
        "record_id": "my-original-physics", "facet": "physics",
        "revision": 1, "depends_on": ["trial-model-source"],
        "document": {
            "kind": "procedural_mesh_physics",
            "base_record_id": "trial-model-source",
            "asset_id": "trial-mesh",
            "body_type": body_type,
            "density_kg_m3": 2000,
            "friction_per_mille": 750,
            "restitution_per_mille": 200,
            "collision_layer": 5,
            "collision_mask": 11,
        },
    })


class Original3dPhysicsShapeTests(unittest.TestCase):
    def test_box_produces_real_collision_shape_and_static_body(self):
        original, authored = mesh_record("box"), source_body()
        result = compile_original_mesh_physics(original, authored)
        scene = result["scene"]
        self.assertIn('type="StaticBody3D"', scene)
        self.assertIn('type="CollisionShape3D"', scene)
        self.assertIn('type="BoxShape3D"', scene)
        self.assertIn("size = Vector3(1.75000000, 2.10000000, 0.85000000)", scene)
        self.assertIn("collision_layer = 5", scene)
        self.assertIn("collision_mask = 11", scene)
        self.assertIn("friction = 0.75000000", scene)
        self.assertIn("bounce = 0.20000000", scene)
        self.assertIn("res://game/frontier/meshes/trial-mesh.glb", scene)
        self.assertEqual(result["metadata"]["collider"]["shape"], "BoxShape3D")
        self.assertFalse(result["metadata"]["actual_collision_observed"])

    def test_equal_radius_sphere_uses_native_godot_sphere_shape(self):
        original = mesh_record("uv_sphere")
        original["document"]["size_mm"] = [1000, 1000, 1000]
        result = compile_original_mesh_physics(reseal(original), source_body())
        self.assertIn('type="SphereShape3D"', result["scene"])
        self.assertIn("radius = 0.50000000", result["scene"])

    def test_ellipsoid_reconstructs_actual_convex_points(self):
        original = mesh_record("uv_sphere")
        result = compile_original_mesh_physics(original, source_body())
        self.assertIn('type="ConvexPolygonShape3D"', result["scene"])
        self.assertIn("PackedVector3Array([Vector3(", result["scene"])
        self.assertGreater(result["metadata"]["collider"]["convex_point_count"], 24)
        self.assertEqual(
            len(result["metadata"]["collider"]["convex_geometry_sha256"]), 64,
        )

    def test_true_circular_cylinder_has_analytic_shape(self):
        original = mesh_record("cylinder")
        original["document"]["size_mm"] = [1200, 1800, 1200]
        result = compile_original_mesh_physics(reseal(original), source_body())
        self.assertIn('type="CylinderShape3D"', result["scene"])
        self.assertIn("radius = 0.60000000", result["scene"])

    def test_elliptical_cylinder_never_claims_wrong_native_radius(self):
        original = mesh_record("cylinder")
        result = compile_original_mesh_physics(original, source_body())
        self.assertIn('type="ConvexPolygonShape3D"', result["scene"])
        self.assertNotIn('type="CylinderShape3D"', result["scene"])

    def test_plane_is_finite_thin_box_and_refuses_rigid_mass(self):
        original = mesh_record("plane")
        result = compile_original_mesh_physics(original, source_body())
        self.assertIn("0.01000000", result["scene"])
        self.assertTrue(result["metadata"]["collider"]["source_is_finite_plane"])
        with self.assertRaises(OriginalMeshPhysicsError):
            compile_original_mesh_physics(original, source_body("rigid"))

    def test_density_derives_positive_rigid_body_mass(self):
        original = mesh_record("box")
        result = compile_original_mesh_physics(original, source_body("rigid"))
        self.assertIn('type="RigidBody3D"', result["scene"])
        self.assertIn("continuous_cd = true", result["scene"])
        self.assertAlmostEqual(
            result["metadata"]["rigid_mass_kg"],
            1.75 * 2.1 * .85 * 2000,
        )

    def test_area3d_has_real_overlap_body_and_no_fake_material(self):
        result = compile_original_mesh_physics(mesh_record(), source_body("area"))
        self.assertIn('type="Area3D"', result["scene"])
        self.assertIn("monitoring = true", result["scene"])
        self.assertNotIn("PhysicsMaterial", result["scene"])
        self.assertIsNone(result["metadata"]["rigid_mass_kg"])
        self.assertFalse(result["metadata"]["actual_collision_observed"])

    def test_optional_lod_scene_is_used_as_visual_child(self):
        source = mesh_record()
        result = compile_original_mesh_physics(
            source, source_body(), has_lod=True,
        )
        self.assertTrue(result["metadata"]["lod_bound"])
        self.assertIn("res://game/frontier/meshes/trial-mesh.lod.tscn", result["scene"])
        self.assertNotIn('path="res://game/frontier/meshes/trial-mesh.glb"',
                         result["scene"])

    def test_same_source_produces_identical_godot_scene(self):
        a = compile_original_mesh_physics(mesh_record(), source_body())
        b = compile_original_mesh_physics(mesh_record(), source_body())
        self.assertEqual(a, b)
        self.assertEqual(
            sha256(a["scene"].encode()).hexdigest(), a["metadata"]["scene_sha256"],
        )

    def test_independent_physics_replay_rebuilds_scene_and_receipts(self):
        original, authored = mesh_record(), source_body()
        candidate = compile_original_mesh_physics(original, authored)
        checked = verify_original_mesh_physics(
            original, authored, candidate["scene"], candidate["metadata"],
        )
        self.assertTrue(checked["collision_shape_replayed_from_original_mesh"])
        self.assertFalse(checked["native_collision_observed"])

    def test_rejects_rehashed_collision_size_tamper(self):
        original, authored = mesh_record(), source_body()
        candidate = compile_original_mesh_physics(original, authored)
        forged = candidate["scene"].replace(
            "1.75000000", "10.7500000",
        )
        with self.assertRaises(OriginalMeshPhysicsError):
            verify_original_mesh_physics(
                original, authored, forged, candidate["metadata"],
            )

    def test_rejects_forged_material_changes(self):
        original, authored = mesh_record(), source_body()
        candidate = compile_original_mesh_physics(original, authored)
        forged = candidate["scene"].replace(
            "friction = 0.75000000", "friction = 0.00000000",
        )
        with self.assertRaises(OriginalMeshPhysicsError):
            verify_original_mesh_physics(
                original, authored, forged, candidate["metadata"],
            )

    def test_rejects_missing_physics_source_dependency(self):
        bad = source_body()
        bad["depends_on"] = []
        with self.assertRaises(OriginalMeshPhysicsError):
            compile_original_mesh_physics(mesh_record(), reseal(bad))

    def test_rejects_boolean_or_overflow_physics_parameters(self):
        for key, bad in (
            ("density_kg_m3", True),
            ("friction_per_mille", 1100),
            ("restitution_per_mille", -1),
            ("collision_layer", 0),
            ("collision_layer", 1 << 30),
            ("collision_mask", True),
            ("body_type", "unsafe_dynamic_execution"),
        ):
            with self.subTest(field=key, value=bad):
                author = source_body()
                author["document"][key] = bad
                with self.assertRaises(OriginalMeshPhysicsError):
                    compile_original_mesh_physics(
                        mesh_record(), reseal(author),
                    )

    def test_duplicate_physics_bodies_for_one_asset_refused(self):
        original = mesh_record()
        a, b = source_body(), source_body("area")
        b["record_id"] = "physics-second"
        reseal(b)
        with self.assertRaises(OriginalMeshPhysicsError):
            compile_original_mesh_physics_collection({
                original["record_id"]: original, a["record_id"]: a,
                b["record_id"]: b,
            })


class PhysicsDescriptors2026Tests(unittest.TestCase):
    def setUp(self):
        self.base = mesh_record("box")
        self.author = source_body()
        self.model = compile_original_mesh(self.base)
        self.result = compile_original_mesh_physics(self.base, self.author)
        self.physics = [{
            "base_record": self.base, "source_record": self.author,
            **self.result,
        }]

    def compile(self):
        return compile_asset_catalog(
            project_id="physics-game", source_head_sha256="0" * 64,
            records={}, meshes=[self.model], physics_assets=self.physics,
        )

    def test_collision_properties_are_machine_retrievable_in_catalog(self):
        data = self.compile()
        self.assertEqual(data["descriptor_count"], 1)
        asset = data["descriptors"][0]
        self.assertIn("godot4_original_collision", asset["engine_targets"])
        physics = asset["metrics"]["physics"]
        self.assertEqual(physics["shape_type"], "BoxShape3D")
        self.assertEqual(physics["material_friction"], .75)
        self.assertEqual(physics["collision_layer"], 5)
        self.assertEqual(physics["collision_mask"], 11)
        self.assertEqual(physics["body_type"], "static")
        self.assertFalse(physics["actual_collision_observed"])
        self.assertTrue(search_asset_catalog(
            data, "trial mesh", kind="procedural_mesh",
        )["results"])

    def test_catalog_replay_requires_real_collision_source_bytes(self):
        data = self.compile()
        proof = verify_asset_catalog(
            catalog_bytes(data), project_id="physics-game",
            source_head_sha256="0" * 64, meshes=[self.model],
            physics_assets=self.physics,
        )
        self.assertEqual(proof["descriptor_count"], 1)

    def test_wrong_physics_attached_to_unrelated_mesh_is_rejected(self):
        different = mesh_record()
        different["document"]["size_mm"][0] += 100
        different = reseal(different)
        with self.assertRaises(AssetDescriptorError):
            compile_asset_catalog(
                project_id="physics-game", source_head_sha256="0" * 64,
                records={}, meshes=[compile_original_mesh(different)],
                physics_assets=self.physics,
            )

    def test_catalog_refuses_tampered_collision_scene(self):
        altered = deepcopy(self.physics)
        altered[0]["scene"] = altered[0]["scene"].replace(
            "StaticBody3D", "Area3D",
        )
        with self.assertRaises(AssetDescriptorError):
            compile_asset_catalog(
                project_id="physics-game", source_head_sha256="0" * 64,
                records={}, meshes=[self.model], physics_assets=altered,
            )


class PhysicalSourceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        exports = root / "exports"
        exports.mkdir()
        self.store = CreatorProjectSourceStore(
            root / "physics.sqlite", project_id="original-game",
            export_root=exports,
        )
        self.addCleanup(self.store.close)

    def create(self, record):
        return self.store.create(build_creator_command(
            "create", project_id="original-game",
            payload={"intent": {
                "record_id": record["record_id"],
                "facet": record["facet"],
                "document": record["document"],
                "depends_on": record["depends_on"],
            }},
        ))

    def test_valid_physics_is_durably_persisted_and_searchable(self):
        self.create(mesh_record())
        self.create(source_body())
        self.assertEqual(self.store.snapshot()["source_count"], 2)
        result = self.store.search_original_assets("trial-mesh")
        self.assertEqual(result["asset_count"], 1)
        self.assertEqual(result["results"][0]["metrics"]["physics"]["body_type"],
                         "static")

    def test_collision_cannot_precede_real_mesh_source(self):
        # Source references are checked before compiler dispatch; missing
        # parents must be rejected without creating a durable source record.
        with self.assertRaises(CreatorSourceError):
            self.create(source_body())
        self.assertEqual(self.store.snapshot()["source_count"], 0)

    def test_physics_source_mutation_cannot_leave_invalid_revision(self):
        self.create(mesh_record())
        self.create(source_body())
        prior = self.store._records["my-original-physics"]["source_sha256"]
        with self.assertRaises(OriginalMeshPhysicsError):
            self.store.edit(build_creator_command(
                "edit", project_id="original-game",
                payload={
                    "target_id": "my-original-physics", "expected_revision": 1,
                    "patch": {"set": {"collision_mask": -1}, "remove": []},
                },
            ))
        self.assertEqual(
            self.store._records["my-original-physics"]["source_sha256"], prior,
        )

    def test_original_mesh_cannot_remove_base_needed_by_collision(self):
        self.create(mesh_record())
        self.create(source_body())
        with self.assertRaises(OriginalMeshPhysicsError):
            self.store.edit(build_creator_command(
                "edit", project_id="original-game",
                payload={
                    "target_id": "trial-model-source", "expected_revision": 1,
                    "patch": {"set": {"asset_id": "renamed-mesh"}, "remove": []},
                },
            ))


if __name__ == "__main__":
    unittest.main()
