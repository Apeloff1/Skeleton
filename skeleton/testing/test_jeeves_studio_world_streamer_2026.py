"""Adversarial Godot 4 source-owned world streamer compilation tests."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import unittest

from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_world_chunks import (
    compile_world_chunk_catalog,
)
from skeleton.jeeves.ai.studio_world_streamer_godot import (
    WorldGodotStreamingError,
    compile_godot_world_streamer,
    verify_godot_world_streamer,
)
from skeleton.testing.test_jeeves_studio_world_chunks_2026 import setup_world


class GodotWorldStreamerTests(unittest.TestCase):
    def actual(self):
        world, chunks = setup_world()
        return world, chunks, compile_godot_world_streamer(world, chunks)

    def test_real_streamer_gd_uses_actual_verified_scene_resource_paths(self):
        _, _, generated = self.actual()
        script = generated["files"]["game/frontier/assets/world_streamer.gd"]
        self.assertIn("extends Node3D", script)
        self.assertIn("res://game/frontier/assets/world-index.json", script)
        self.assertIn("res://game/frontier/assets/world-chunks.json", script)
        self.assertIn("PackedScene", script)
        self.assertIn("node.position = _vec_mm", script)
        self.assertIn("node.rotation_degrees = Vector3", script)
        self.assertIn("node.scale = Vector3.ONE", script)
        self.assertIn("node.queue_free()", script)
        self.assertIn("relevant.keys()", script)
        self.assertIn("instantiate_per_frame", script)
        self.assertIn("var camera := get_viewport().get_camera_3d()", script)

    def test_standalone_component_does_not_double_spawn_default_world(self):
        _, _, generated = self.actual()
        script = generated["files"]["game/frontier/assets/world_streamer.gd"]
        self.assertIn("Instantiate ONLY instead", script)
        self.assertEqual(len(generated["files"]), 2)
        self.assertNotIn("game/frontier/expedition.tscn", generated["files"])
        self.assertTrue(
            generated["receipt"]["streamer_requires_explicit_instantiation"],
        )
        self.assertTrue(generated["receipt"]["static_world_scene_preserved"])

    def test_real_godot_tscn_instantiates_bound_script(self):
        _, _, generated = self.actual()
        scene = generated["files"]["game/frontier/assets/world_streamer.tscn"]
        self.assertIn('[node name="OriginalWorldStreamer" type="Node3D"]', scene)
        self.assertIn('type="Script"', scene)
        self.assertIn("res://game/frontier/assets/world_streamer.gd", scene)
        self.assertIn('script = ExtResource("1")', scene)

    def test_exact_same_source_builds_identical_godot_files(self):
        source, cells, generated = self.actual()
        self.assertEqual(generated, compile_godot_world_streamer(source, cells))
        for filename, data in generated["files"].items():
            self.assertEqual(
                generated["receipt"]["resources"][filename],
                sha256(data.encode("utf-8")).hexdigest(),
            )

    def test_distinct_world_revision_produces_distinct_script_source_receipt(self):
        source, cells, first = self.actual()
        next_world = deepcopy(source)
        next_world["source_head_sha256"] = "b" * 64
        next_world["receipt_sha256"] = digest({
            k: v for k, v in next_world.items() if k != "receipt_sha256"
        })
        next_cells = compile_world_chunk_catalog(next_world)
        latter = compile_godot_world_streamer(next_world, next_cells)
        self.assertNotEqual(
            first["receipt"]["receipt_sha256"],
            latter["receipt"]["receipt_sha256"],
        )

    def test_independent_source_replay_accepts_only_exact_godot_script(self):
        world, chunks, emitted = self.actual()
        checked = verify_godot_world_streamer(
            world, chunks, emitted["files"], emitted["receipt"],
        )
        self.assertEqual(checked["files_checked"], 2)
        self.assertTrue(checked["source_text_reproduced"])
        self.assertFalse(checked["native_streaming_executed"])

    def test_forged_scene_runtime_injection_is_rejected(self):
        world, chunks, emitted = self.actual()
        forged = deepcopy(emitted["files"])
        forged["game/frontier/assets/world_streamer.gd"] += (
            "\nfunc _run_unauthorized() -> void:\n    pass\n"
        )
        with self.assertRaises(WorldGodotStreamingError):
            verify_godot_world_streamer(
                world, chunks, forged, emitted["receipt"],
            )

    def test_metadata_forged_engine_execution_is_refused(self):
        world, chunks, emitted = self.actual()
        altered = deepcopy(emitted["receipt"])
        altered["source_runtime_streaming_executed"] = True
        altered["receipt_sha256"] = digest({
            k: v for k, v in altered.items() if k != "receipt_sha256"
        })
        with self.assertRaises(WorldGodotStreamingError):
            verify_godot_world_streamer(world, chunks, emitted["files"], altered)

    def test_stale_world_index_and_chunk_manifest_are_denied(self):
        index, cells, _ = self.actual()
        swapped = deepcopy(index)
        swapped["instances"][0]["asset_id"] = "different-asset"
        swapped["receipt_sha256"] = digest({
            k: v for k, v in swapped.items() if k != "receipt_sha256"
        })
        with self.assertRaises(WorldGodotStreamingError):
            compile_godot_world_streamer(swapped, cells)

    def test_physics_streamer_preserves_original_colliders(self):
        world, cells = setup_world(physical=True)
        emitted = compile_godot_world_streamer(world, cells)
        self.assertIn("res://", emitted["files"]["game/frontier/assets/world_streamer.gd"])
        self.assertNotIn("StaticBody3D", emitted["files"]["game/frontier/assets/world_streamer.gd"])
        self.assertTrue(emitted["receipt"]["static_world_scene_preserved"])

    def test_empty_world_streamer_is_valid_but_not_a_fake_gameplay_proof(self):
        from skeleton.jeeves.ai.studio_original_mesh_placements import compile_original_mesh_placements
        from skeleton.jeeves.ai.studio_original_mesh import compile_original_mesh
        from skeleton.jeeves.ai.studio_asset_descriptors import compile_asset_catalog
        from skeleton.jeeves.ai.studio_world_spatial_index import compile_world_spatial_index
        from skeleton.testing.test_jeeves_studio_asset_compilers_2026 import mesh_record
        base = mesh_record()
        catalog = compile_asset_catalog(
            project_id="world-game", source_head_sha256="a" * 64,
            records={}, meshes=[compile_original_mesh(base)],
        )
        scenes = compile_original_mesh_placements({})
        world = compile_world_spatial_index(
            project_id="world-game", source_head_sha256="a" * 64,
            catalog=catalog, placements=scenes["metadata"],
        )
        cells = compile_world_chunk_catalog(world)
        emitted = compile_godot_world_streamer(world, cells)
        self.assertFalse(emitted["receipt"]["source_runtime_streaming_executed"])
        self.assertEqual(emitted["receipt"]["per_frame_scene_instantiation_budget"], 4)


if __name__ == "__main__":
    unittest.main()
