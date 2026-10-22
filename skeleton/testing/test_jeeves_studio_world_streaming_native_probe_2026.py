"""Independent source and host-native camera streaming verification regressions.

The faked native observations below validate *receipt rejection logic only*.
A true native success receipt requires an installed Godot 4 subprocess.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from unittest import TestCase

from skeleton.jeeves.ai.studio_asset_descriptors import compile_asset_catalog
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_original_mesh import compile_original_mesh
from skeleton.jeeves.ai.studio_original_mesh_placements import (
    attach_authored_meshes_to_expedition,
)
from skeleton.jeeves.ai.studio_world_spatial_index import (
    compile_world_spatial_index, spatial_index_bytes,
)
from skeleton.jeeves.ai.studio_world_chunks import (
    compile_world_chunk_catalog, world_chunk_catalog_bytes,
)
from skeleton.jeeves.ai.studio_world_streaming_activation import (
    replace_static_meshes_with_streaming, streaming_policy_source_bytes,
)
from skeleton.jeeves.ai.studio_world_streaming_native_probe import (
    NativeWorldStreamError, PREFIX, compile_native_world_stream_probe,
    verify_native_world_stream_output,
)
from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCENE
from skeleton.testing.test_jeeves_studio_world_streaming_activation_2026 import (
    approved_world, streaming_source,
)


def candidate_fixture(*, enabled: bool = True) -> dict:
    from skeleton.jeeves.ai.studio_world_streaming_activation import (
        compile_world_streaming_activation,
    )

    records, placements = approved_world()
    original = records["trial-model-source"]
    catalog = compile_asset_catalog(
        project_id="stream-test", source_head_sha256="a" * 64,
        records=records, meshes=[compile_original_mesh(original)],
    )
    world = compile_world_spatial_index(
        project_id="stream-test", source_head_sha256="a" * 64,
        catalog=catalog, placements=placements["metadata"],
    )
    chunks = compile_world_chunk_catalog(world)
    if enabled:
        src = streaming_source()
        records[src["record_id"]] = src
    policy = compile_world_streaming_activation(records, placements["metadata"])
    static = attach_authored_meshes_to_expedition(_GODOT_SCENE, placements)
    scene = replace_static_meshes_with_streaming(static, policy["receipt"])
    content = {
        "game/frontier/expedition.tscn": scene.encode("utf-8"),
        "game/frontier/assets/world-index.json": spatial_index_bytes(world),
        "game/frontier/assets/world-chunks.json": world_chunk_catalog_bytes(chunks),
    }
    authored_policy = streaming_policy_source_bytes(policy)
    if authored_policy is not None:
        content["game/frontier/assets/world_streaming.source.json"] = authored_policy
    receipt = {
        "schema_version": "stream-test-candidate",
        "source_head_sha256": "a" * 64,
        "world_spatial_index_sha256": sha256(
            content["game/frontier/assets/world-index.json"]
        ).hexdigest(),
        "world_chunk_catalog_sha256": sha256(
            content["game/frontier/assets/world-chunks.json"]
        ).hexdigest(),
        "packaged_original_mesh_placements": placements["metadata"],
        "world_streaming_policy": policy["receipt"],
        "godot_file_hashes": {
            name: sha256(data).hexdigest() for name, data in content.items()
        },
    }
    receipt["receipt_sha256"] = digest(receipt)
    return {
        "files": {"game/frontier/expedition.tscn": scene},
        "binary_assets": {
            name: raw for name, raw in content.items()
            if name != "game/frontier/expedition.tscn"
        },
        "receipt": receipt,
    }


def simulated_native_log(compiled: dict) -> str:
    expected = compiled["expected"]
    observed = {
        "candidate_receipt_sha256": expected["candidate_receipt_sha256"],
        "world_receipt_sha256": expected["world_receipt_sha256"],
        "chunk_receipt_sha256": expected["chunk_receipt_sha256"],
        "activation_receipt_sha256": expected["activation_receipt_sha256"],
        "near_instance_ids": [expected["target_id"]],
        "far_instance_ids": expected["pinned_instance_ids"],
        "target_id": expected["target_id"],
        "target_spawned": True,
        "target_unloaded": True,
        "stateful_instances_retained": True,
    }
    return PREFIX + json.dumps(observed, sort_keys=True)


def rehash(candidate: dict) -> None:
    receipt = candidate["receipt"]
    receipt["receipt_sha256"] = digest({
        key: value for key, value in receipt.items()
        if key != "receipt_sha256"
    })


class NativeWorldSourceTests(TestCase):
    def test_valid_compiler_generates_real_godot_camera_transition_program(self):
        result = compile_native_world_stream_probe(candidate_fixture())
        script = result["script"]
        self.assertIn("extends SceneTree", script)
        self.assertIn('load("res://game/frontier/expedition.tscn")', script)
        self.assertIn('get_node_or_null("OriginalMeshInstances")', script)
        self.assertIn('camera.global_position = Vector3(', script)
        self.assertIn('streamer._process(0.016)', script)
        self.assertIn("node.get_parent() != streamer", script)
        self.assertIn("pinned physics body was never instantiated", script)
        self.assertIn("stateful body was evicted or rebuilt", script)
        self.assertIn("offscreen static mesh was not unloaded", script)
        self.assertFalse(result["native_executed"])
        self.assertEqual(result["script_sha256"], sha256(script.encode()).hexdigest())

    def test_exact_source_is_stable_across_repeated_compilation(self):
        left, right = candidate_fixture(), candidate_fixture()
        self.assertEqual(
            compile_native_world_stream_probe(left),
            compile_native_world_stream_probe(right),
        )

    def test_statically_instanced_game_is_not_a_streaming_success(self):
        with self.assertRaises(NativeWorldStreamError):
            compile_native_world_stream_probe(candidate_fixture(enabled=False))

    def test_forged_game_root_is_rejected_even_with_updated_sha(self):
        candidate = candidate_fixture()
        candidate["files"]["game/frontier/expedition.tscn"] = (
            candidate["files"]["game/frontier/expedition.tscn"].replace(
                "view_radius_m = 250.0", "view_radius_m = 10.0",
            )
        )
        raw = candidate["files"]["game/frontier/expedition.tscn"].encode()
        candidate["receipt"]["godot_file_hashes"][
            "game/frontier/expedition.tscn"
        ] = sha256(raw).hexdigest()
        rehash(candidate)
        with self.assertRaises(NativeWorldStreamError):
            compile_native_world_stream_probe(candidate)

    def test_invalid_original_candidate_receipt_is_rejected(self):
        candidate = candidate_fixture()
        candidate["receipt"]["receipt_sha256"] = "0" * 64
        with self.assertRaises(NativeWorldStreamError):
            compile_native_world_stream_probe(candidate)

    def test_forged_world_source_bytes_are_rejected(self):
        candidate = candidate_fixture()
        path = "game/frontier/assets/world-index.json"
        raw = candidate["binary_assets"][path]
        candidate["binary_assets"][path] = raw.replace(
            b'"instance_count":1', b'"instance_count":0',
        )
        with self.assertRaises(NativeWorldStreamError):
            compile_native_world_stream_probe(candidate)

    def test_unapproved_chunk_source_is_rejected(self):
        candidate = candidate_fixture()
        path = "game/frontier/assets/world-chunks.json"
        candidate["binary_assets"][path] = b"{}"
        with self.assertRaises(NativeWorldStreamError):
            compile_native_world_stream_probe(candidate)

    def test_forged_activation_source_is_rejected(self):
        candidate = candidate_fixture()
        path = "game/frontier/assets/world_streaming.source.json"
        candidate["binary_assets"][path] = b"{}"
        with self.assertRaises(NativeWorldStreamError):
            compile_native_world_stream_probe(candidate)

    def test_missing_source_bytes_fail_closed(self):
        for filename in (
            "game/frontier/assets/world-index.json",
            "game/frontier/assets/world-chunks.json",
            "game/frontier/assets/world_streaming.source.json",
        ):
            candidate = candidate_fixture()
            candidate["binary_assets"].pop(filename)
            with self.subTest(filename=filename):
                with self.assertRaises(NativeWorldStreamError):
                    compile_native_world_stream_probe(candidate)

    def test_error_source_root_without_streaming_policy_is_not_canonical(self):
        candidate = candidate_fixture()
        candidate["receipt"]["world_streaming_policy"]["enabled"] = False
        rehash(candidate)
        with self.assertRaises(NativeWorldStreamError):
            compile_native_world_stream_probe(candidate)


class NativeWorldObservationTests(TestCase):
    def compiled(self):
        return compile_native_world_stream_probe(candidate_fixture())

    def verified(self, compiled: dict, output: str) -> dict:
        return verify_native_world_stream_output(
            compiled, output, executable_sha256="f" * 64,
        )

    def test_matching_simulation_checks_observation_shape_not_actual_process(self):
        compiled = self.compiled()
        proof = self.verified(compiled, simulated_native_log(compiled))
        self.assertTrue(proof["observed_camera_driven_instantiation"])
        self.assertTrue(proof["observed_camera_driven_unloading"])
        self.assertEqual(proof["near_instantiated_count"], 1)
        self.assertEqual(proof["far_instantiated_count"], 0)
        self.assertFalse(proof["observed_collision_contacts"])
        self.assertFalse(proof["observed_gpu_residency"])
        self.assertFalse(proof["observed_rendered_pixels"])

    def test_changed_project_receipt_never_passes_even_if_events_look_correct(self):
        compiled = self.compiled()
        log = simulated_native_log(compiled).replace(
            compiled["expected"]["candidate_receipt_sha256"], "a" * 64,
        )
        with self.assertRaises(NativeWorldStreamError):
            self.verified(compiled, log)

    def test_forged_world_receipt_never_passes(self):
        compiled = self.compiled()
        log = simulated_native_log(compiled).replace(
            compiled["expected"]["world_receipt_sha256"], "b" * 64,
        )
        with self.assertRaises(NativeWorldStreamError):
            self.verified(compiled, log)

    def test_native_missing_transition_event_is_rejected(self):
        compiled = self.compiled()
        log = simulated_native_log(compiled).replace(
            '"target_unloaded": true', '"target_unloaded": false',
        )
        with self.assertRaises(NativeWorldStreamError):
            self.verified(compiled, log)

    def test_extra_foreign_instance_in_observation_is_rejected(self):
        compiled = self.compiled()
        log = simulated_native_log(compiled).replace(
            '"near_instance_ids": ["temple-doorway"]',
            '"near_instance_ids": ["temple-doorway", "foreign"]',
        )
        with self.assertRaises(NativeWorldStreamError):
            self.verified(compiled, log)

    def test_native_missing_instantiate_event_is_rejected(self):
        compiled = self.compiled()
        log = simulated_native_log(compiled).replace(
            '"target_spawned": true', '"target_spawned": false',
        )
        with self.assertRaises(NativeWorldStreamError):
            self.verified(compiled, log)

    def test_duplicate_success_event_is_rejected(self):
        compiled = self.compiled()
        log = simulated_native_log(compiled)
        with self.assertRaises(NativeWorldStreamError):
            self.verified(compiled, log + "\n" + log)

    def test_native_import_errors_never_pass_just_because_receipt_exists(self):
        compiled = self.compiled()
        log = "SCRIPT ERROR: invalid scene\n" + simulated_native_log(compiled)
        with self.assertRaises(NativeWorldStreamError):
            self.verified(compiled, log)

    def test_no_real_native_stdout_cannot_claim_success(self):
        with self.assertRaises(NativeWorldStreamError):
            self.verified(self.compiled(), "")

    def test_overlong_host_log_is_rejected(self):
        compiled = self.compiled()
        with self.assertRaises(NativeWorldStreamError):
            self.verified(compiled, simulated_native_log(compiled) + "x" * 2_100_000)

    def test_mutated_native_target_name_is_rejected(self):
        compiled = self.compiled()
        log = simulated_native_log(compiled).replace(
            '"target_id": "temple-doorway"', '"target_id": "other"',
        )
        with self.assertRaises(NativeWorldStreamError):
            self.verified(compiled, log)


if __name__ == "__main__":
    import unittest
    unittest.main()
