"""Adversarial exact-candidate Godot 4 3D runtime probe and routing tests.

Pure tests verify receipts and Godot-script structure. The integration mock
only demonstrates correct routing; it does NOT claim Godot actually ran.
Native mesh imports are certified solely by the host-authorized executable.
"""
from __future__ import annotations

from copy import deepcopy
import json
from unittest import TestCase
from unittest.mock import patch

from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_original_mesh_native_probe import (
    MeshEngineProbeError, PREFIX,
    compile_native_mesh_probe, verify_native_mesh_probe_output,
)
from skeleton.jeeves.ai.studio_frontier_godot_package import (
    run_original_game_native_playthrough,
)
from skeleton.testing.test_jeeves_studio_frontier_source_compile import (
    RealGodotSourceBuildTests,
)


def fake_candidate(*, mesh_ids: tuple[str, ...] = ("temple-stone",),
                   physical: bool = True, placed: bool = True) -> dict:
    if physical and not mesh_ids:
        raise ValueError("a physics record requires a real mesh")
    receipt = {
        "packaged_original_meshes": [
            {"asset_id": asset} for asset in mesh_ids
        ],
        "packaged_original_mesh_physics": (
            [{"asset_id": mesh_ids[0]}] if physical else []
        ),
        "packaged_original_mesh_lods": [],
        "packaged_original_mesh_placements": {
            "instances": [{
                "asset_id": mesh_ids[0], "instance_id": "temple-entry",
                "visual_or_physics": "physics" if physical else "visual",
                "position_mm": [1200, 300, -900],
                "scale_per_mille": 1500,
            }] if placed and mesh_ids else [],
        },
    }
    receipt["receipt_sha256"] = digest(receipt)
    return {"receipt": receipt}


def observed_log(compiled: dict) -> str:
    expected = compiled["expected"]
    observed = {
        "candidate_sha256": expected["candidate_sha256"],
        "mesh_ids": expected["mesh_ids"],
        "physics_ids": expected["physics_ids"],
        "instance_ids": [
            entry["instance_id"] for entry in expected["instances"]
        ],
        "imported_mesh_count": len(expected["mesh_ids"]),
        "active_physics_bodies": len(expected["physics_ids"]),
        "game_instances": len(expected["instances"]),
    }
    return PREFIX + json.dumps(observed, sort_keys=True)


def verify(compiled: dict, raw_log: str) -> dict:
    return verify_native_mesh_probe_output(
        compiled, raw_log,
        executable_sha256="a" * 64,
        import_log_sha256="b" * 64,
    )


class MeshEngineProbeCompilerTests(TestCase):
    def test_script_instantiates_actual_imported_glb_geometry(self):
        compiled = compile_native_mesh_probe(fake_candidate())
        source = compiled["script"]
        self.assertIn("extends SceneTree", source)
        self.assertIn('".glb"', source)
        self.assertIn("model.instantiate()", source)
        self.assertIn('"MeshInstance3D"', source)
        self.assertIn("get_surface_count()", source)
        self.assertIn('".physics.tscn"', source)
        self.assertIn("CollisionShape3D", source)
        self.assertIn("get_node_or_null(instance_path)", source)
        self.assertIn("source-authored game transform diverges", source)
        self.assertIn("quit(1)", source)
        self.assertIn(PREFIX, source)
        self.assertEqual(len(compiled["probe_script_sha256"]), 64)
        self.assertFalse(compiled["native_engine_executed"])

    def test_source_identical_across_repeated_compilation(self):
        a = fake_candidate()
        self.assertEqual(
            compile_native_mesh_probe(a), compile_native_mesh_probe(deepcopy(a)),
        )

    def test_godot_probe_identifier_source_is_escaped(self):
        bad = fake_candidate()
        bad["receipt"]["packaged_original_meshes"][0]["asset_id"] = (
            'demon\"; OS.execute("delete")'
        )
        bad["receipt"]["receipt_sha256"] = digest({
            key: value for key, value in bad["receipt"].items()
            if key != "receipt_sha256"
        })
        with self.assertRaises(MeshEngineProbeError):
            compile_native_mesh_probe(bad)

    def test_probe_rejects_unauthorized_model_without_original_receipt(self):
        bad = fake_candidate()
        bad["receipt"]["receipt_sha256"] = "0" * 64
        with self.assertRaises(MeshEngineProbeError):
            compile_native_mesh_probe(bad)

    def test_probe_refuses_missing_actual_glb_source(self):
        with self.assertRaises(MeshEngineProbeError):
            compile_native_mesh_probe(fake_candidate(mesh_ids=(), physical=False))

    def test_probe_rejects_duplicate_mesh_asset_ids(self):
        with self.assertRaises(MeshEngineProbeError):
            compile_native_mesh_probe(fake_candidate(
                mesh_ids=("stone", "stone"), physical=False, placed=False,
            ))

    def test_probe_rejects_missing_physics_asset_reference(self):
        source = fake_candidate()
        source["receipt"]["packaged_original_mesh_physics"] = [
            {"asset_id": "not-a-model"}
        ]
        source["receipt"]["receipt_sha256"] = digest({
            key: value for key, value in source["receipt"].items()
            if key != "receipt_sha256"
        })
        with self.assertRaises(MeshEngineProbeError):
            compile_native_mesh_probe(source)

    def test_probe_rejects_placement_claiming_wrong_physics_kind(self):
        source = fake_candidate(physical=False)
        source["receipt"]["packaged_original_mesh_placements"][
            "instances"
        ][0]["visual_or_physics"] = "physics"
        source["receipt"]["receipt_sha256"] = digest({
            key: value for key, value in source["receipt"].items()
            if key != "receipt_sha256"
        })
        with self.assertRaises(MeshEngineProbeError):
            compile_native_mesh_probe(source)

    def test_replay_parses_unique_complete_native_observation(self):
        compiled = compile_native_mesh_probe(fake_candidate())
        result = verify(compiled, observed_log(compiled))
        self.assertEqual(result["imported_geometry_mesh_count"], 1)
        self.assertEqual(result["instanced_3d_physics_bodies"], 1)
        self.assertEqual(result["source_game_scene_instances"], 1)
        self.assertTrue(result["source_meshes_imported_in_godot"])
        self.assertTrue(result["native_scene_instances_examined"])
        self.assertFalse(result["native_rendered_pixels_observed"])
        self.assertFalse(result["native_physics_contacts_observed"])

    def test_unplaced_mesh_still_requires_real_import(self):
        compiled = compile_native_mesh_probe(fake_candidate(
            physical=False, placed=False,
        ))
        result = verify(compiled, observed_log(compiled))
        self.assertEqual(result["imported_geometry_mesh_count"], 1)
        self.assertEqual(result["source_game_scene_instances"], 0)
        self.assertEqual(result["instanced_3d_physics_bodies"], 0)

    def test_native_log_claiming_extra_mesh_is_rejected(self):
        compiled = compile_native_mesh_probe(fake_candidate())
        log = observed_log(compiled).replace(
            '"mesh_ids": ["temple-stone"]',
            '"mesh_ids": ["temple-stone", "unexpected"]',
        )
        with self.assertRaises(MeshEngineProbeError):
            verify(compiled, log)

    def test_native_log_with_forged_candidate_receipt_is_rejected(self):
        compiled = compile_native_mesh_probe(fake_candidate())
        log = observed_log(compiled).replace(
            compiled["expected"]["candidate_sha256"],
            "f" * 64,
        )
        with self.assertRaises(MeshEngineProbeError):
            verify(compiled, log)

    def test_native_log_with_missing_physics_body_is_rejected(self):
        compiled = compile_native_mesh_probe(fake_candidate())
        log = observed_log(compiled).replace(
            '"physics_ids": ["temple-stone"]', '"physics_ids": []',
        ).replace('"active_physics_bodies": 1', '"active_physics_bodies": 0')
        with self.assertRaises(MeshEngineProbeError):
            verify(compiled, log)

    def test_native_log_with_wrong_placement_transform_count_is_rejected(self):
        compiled = compile_native_mesh_probe(fake_candidate())
        log = observed_log(compiled).replace('"game_instances": 1', '"game_instances": 2')
        with self.assertRaises(MeshEngineProbeError):
            verify(compiled, log)

    def test_probe_denies_replayed_or_duplicate_stdout(self):
        compiled = compile_native_mesh_probe(fake_candidate())
        log = observed_log(compiled)
        with self.assertRaises(MeshEngineProbeError):
            verify(compiled, log + "\n" + log)

    def test_probe_denies_missing_native_stdout(self):
        compiled = compile_native_mesh_probe(fake_candidate())
        with self.assertRaises(MeshEngineProbeError):
            verify(compiled, "Imported mesh but no measurement")

    def test_probe_denies_oversize_native_output(self):
        compiled = compile_native_mesh_probe(fake_candidate())
        with self.assertRaises(MeshEngineProbeError):
            verify(compiled, observed_log(compiled) + "x" * 2_000_000)


class ExactGameSourceRunnerRoutingTests(TestCase):
    """Route tests use a fake runner only to inspect which candidate was sent."""

    setUp = RealGodotSourceBuildTests.setUp
    create = RealGodotSourceBuildTests.create
    populate_3d = RealGodotSourceBuildTests.populate_3d

    def test_real_original_mesh_never_uses_baseline_native_game(self):
        self.populate_3d()
        self.create("real-scene-glb", "asset_forge", {
            "kind": "procedural_mesh", "asset_id": "beacon",
            "primitive": "box", "size_mm": [600, 1000, 900],
            "segments": 8, "color_rgba": "#669988ff",
            "metallic_per_mille": 80, "roughness_per_mille": 700,
        }, depends=("config-3d",))
        captured = []

        def exact(candidate, world, player, **kwargs):
            captured.append(candidate)
            return {
                "world_digest": world.digest,
                "native_process_executed": True,
                "native_gameplay_consistent": True,
                "completed": True,
                "receipt_digest": "0" * 64,
                "native_executable_sha256": "1" * 64,
                "native_log_sha256": "2" * 64,
                "observed_replay_receipt": "3" * 64,
                "native_mesh_probe_receipt_sha256": "4" * 64,
                "actual_godot_meshes_imported": 1,
                "actual_godot_physics_bodies_instantiated": 0,
                "actual_godot_scene_mesh_instances": 0,
            }

        with (
            patch(
                "skeleton.jeeves.game_frontier_expedition_native_runner."
                "run_headless_expedition",
                side_effect=AssertionError("baseline cannot attest authored GLB"),
            ),
            patch(
                "skeleton.jeeves.ai.studio_sprite_bound_native_runner."
                "run_exact_original_candidate_native_expedition",
                side_effect=exact,
            ),
        ):
            evidence = run_original_game_native_playthrough(
                "new-game", self.owner._records,
                source_head_sha256=self.owner.head_identity(),
                godot_executable="/not/an/engine",
            )
        self.assertEqual(len(captured), 1)
        self.assertIn("game/frontier/meshes/beacon.glb",
                      captured[0]["binary_assets"])
        self.assertEqual(evidence["native_meshes_imported_observed"], 1)
        self.assertFalse(evidence["native_collision_events_observed"])
        self.assertFalse(evidence["native_visual_output_independently_observed"])

    def test_real_mesh_with_placement_never_uses_baseline_project(self):
        self.populate_3d()
        self.create("original-statue", "asset_forge", {
            "kind": "procedural_mesh", "asset_id": "statue",
            "primitive": "box", "size_mm": [900, 1100, 600],
            "segments": 6, "color_rgba": "#aabbccff",
            "metallic_per_mille": 0, "roughness_per_mille": 850,
        }, depends=("config-3d",))
        self.create("statue-placement", "scene_forge", {
            "kind": "original_mesh_instance", "instance_id": "statue-one",
            "base_record_id": "original-statue", "asset_id": "statue",
            "physics_record_id": None, "position_mm": [1000, 0, 1500],
            "rotation_deg": [0, 45, 0], "scale_per_mille": 1000,
        }, depends=("original-statue",))
        inspected = []
        def exact(candidate, world, player, **kwargs):
            inspected.append(candidate["receipt"]["packaged_original_mesh_placements"])
            raise RuntimeError("host native probe unavailable; no pass receipt")
        with (
            patch(
                "skeleton.jeeves.game_frontier_expedition_native_runner."
                "run_headless_expedition",
                side_effect=AssertionError("no fallback allowed"),
            ),
            patch(
                "skeleton.jeeves.ai.studio_sprite_bound_native_runner."
                "run_exact_original_candidate_native_expedition",
                side_effect=exact,
            ),
        ):
            with self.assertRaises(RuntimeError):
                run_original_game_native_playthrough(
                    "new-game", self.owner._records,
                    source_head_sha256=self.owner.head_identity(),
                    godot_executable="/not/an/engine",
                )
        self.assertEqual(inspected[0]["instance_count"], 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
