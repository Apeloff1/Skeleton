"""Authored nonduplicating Godot large-world streaming activation tests."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_original_mesh_placements import (
    attach_authored_meshes_to_expedition, compile_original_mesh_placements,
)
from skeleton.jeeves.ai.studio_world_streaming_activation import (
    WorldStreamingActivationError, compile_world_streaming_activation,
    recover_exact_static_mesh_scene, replace_static_meshes_with_streaming,
    streaming_policy_source_bytes, verify_streaming_policy_archive,
    STATIC_LINK, STREAM_LINK,
)
from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCENE
from skeleton.testing.test_jeeves_studio_asset_compilers_2026 import (
    mesh_record, reseal,
)
from skeleton.testing.test_jeeves_studio_mesh_placements_2026 import instance_record


def approved_world():
    model = mesh_record()
    placed = instance_record()
    records = {model["record_id"]: model, placed["record_id"]: placed}
    placements = compile_original_mesh_placements(records)
    return records, placements


def streaming_source():
    return reseal({
        "record_id": "streaming-config", "facet": "scene_forge",
        "revision": 1, "depends_on": ["original-scene-placement"],
        "document": {
            "kind": "original_world_streaming_policy",
            "mode": "replace_static",
            "view_radius_m": 250,
            "instantiate_per_frame": 7,
        },
    })


class StreamerActivationSourceTests(unittest.TestCase):
    def compile(self):
        records, placements = approved_world()
        config = streaming_source()
        records[config["record_id"]] = config
        return compile_world_streaming_activation(
            records, placements["metadata"],
        ), placements

    def test_explicit_authored_policy_replaces_not_duplicates_existing_meshes(self):
        compiled, placements = self.compile()
        root = attach_authored_meshes_to_expedition(_GODOT_SCENE, placements)
        active = replace_static_meshes_with_streaming(root, compiled["receipt"])
        self.assertIn(STREAM_LINK, active)
        self.assertNotIn(STATIC_LINK, active)
        self.assertIn("view_radius_m = 250.0", active)
        self.assertIn("instantiate_per_frame = 7", active)
        self.assertEqual(active.count("OriginalMeshInstances"), 1)
        self.assertEqual(
            recover_exact_static_mesh_scene(active, compiled["receipt"]), root,
        )
        self.assertFalse(compiled["receipt"]["godot_streaming_observed"])

    def test_no_policy_preserves_original_static_game(self):
        records, placed = approved_world()
        compiled = compile_world_streaming_activation(
            records, placed["metadata"],
        )
        root = attach_authored_meshes_to_expedition(_GODOT_SCENE, placed)
        self.assertFalse(compiled["receipt"]["enabled"])
        self.assertIsNone(streaming_policy_source_bytes(compiled))
        self.assertEqual(
            replace_static_meshes_with_streaming(root, compiled["receipt"]), root,
        )
        self.assertFalse(
            verify_streaming_policy_archive(
                None, compiled["receipt"], placed["metadata"], root,
            )["enabled"]
        )

    def test_author_source_replays_exact_canonical_json_and_root(self):
        compiled, placements = self.compile()
        source = streaming_policy_source_bytes(compiled)
        self.assertEqual(
            json.dumps(json.loads(source), sort_keys=True, ensure_ascii=True,
                       separators=(",", ":")).encode("utf-8"), source,
        )
        root = attach_authored_meshes_to_expedition(_GODOT_SCENE, placements)
        active = replace_static_meshes_with_streaming(root, compiled["receipt"])
        evidence = verify_streaming_policy_archive(
            source, compiled["receipt"], placements["metadata"], active,
        )
        self.assertTrue(evidence["enabled"])
        self.assertEqual(evidence["static_root"], root)

    def test_changed_camera_distance_replays_only_with_new_source_revision(self):
        compiled, placed = self.compile()
        records, _ = approved_world()
        edited = streaming_source()
        edited["document"]["view_radius_m"] = 480
        records[edited["record_id"]] = reseal(edited)
        revised = compile_world_streaming_activation(
            records, placed["metadata"],
        )
        self.assertNotEqual(
            compiled["receipt"]["receipt_sha256"],
            revised["receipt"]["receipt_sha256"],
        )
        self.assertNotEqual(
            streaming_policy_source_bytes(compiled),
            streaming_policy_source_bytes(revised),
        )

    def test_missing_source_dependency_and_wrong_source_identity_denied(self):
        recs, placed = approved_world()
        invalid = streaming_source()
        invalid["depends_on"] = []
        recs[invalid["record_id"]] = reseal(invalid)
        with self.assertRaises(WorldStreamingActivationError):
            compile_world_streaming_activation(recs, placed["metadata"])

    def test_duplicate_streamers_refused_before_any_source_commit(self):
        recs, placed = approved_world()
        first = streaming_source()
        other = deepcopy(first)
        other["record_id"] = "second-streamer"
        recs[first["record_id"]] = first
        recs[other["record_id"]] = reseal(other)
        with self.assertRaises(WorldStreamingActivationError):
            compile_world_streaming_activation(recs, placed["metadata"])

    def test_out_of_range_budget_distance_boolean_fail_closed(self):
        for name, value in (
            ("view_radius_m", True), ("view_radius_m", 5001),
            ("instantiate_per_frame", 0),
            ("instantiate_per_frame", True),
            ("instantiate_per_frame", 33),
        ):
            with self.subTest(name=name, value=value):
                recs, placed = approved_world()
                invalid = streaming_source()
                invalid["document"][name] = value
                recs[invalid["record_id"]] = reseal(invalid)
                with self.assertRaises(WorldStreamingActivationError):
                    compile_world_streaming_activation(recs, placed["metadata"])

    def test_unapproved_static_root_injection_is_rejected(self):
        compiled, placed = self.compile()
        root = attach_authored_meshes_to_expedition(_GODOT_SCENE, placed)
        with self.assertRaises(WorldStreamingActivationError):
            replace_static_meshes_with_streaming(
                root.replace(STATIC_LINK, ""), compiled["receipt"],
            )

    def test_published_active_root_change_is_rejected_even_with_new_hash(self):
        compiled, placed = self.compile()
        root = attach_authored_meshes_to_expedition(_GODOT_SCENE, placed)
        active = replace_static_meshes_with_streaming(root, compiled["receipt"])
        forged = active.replace("view_radius_m = 250.0",
                                "view_radius_m = 1250.0")
        with self.assertRaises(WorldStreamingActivationError):
            verify_streaming_policy_archive(
                streaming_policy_source_bytes(compiled),
                compiled["receipt"], placed["metadata"], forged,
            )

    def test_static_or_enabled_forged_source_mismatch_denied(self):
        compiled, placed = self.compile()
        active = replace_static_meshes_with_streaming(
            attach_authored_meshes_to_expedition(_GODOT_SCENE, placed),
            compiled["receipt"],
        )
        with self.assertRaises(WorldStreamingActivationError):
            verify_streaming_policy_archive(
                None, compiled["receipt"], placed["metadata"], active,
            )
        altered = deepcopy(compiled["receipt"])
        altered["view_radius_m"] = 25
        altered["receipt_sha256"] = digest({
            k: v for k, v in altered.items() if k != "receipt_sha256"
        })
        with self.assertRaises(WorldStreamingActivationError):
            verify_streaming_policy_archive(
                streaming_policy_source_bytes(compiled),
                altered, placed["metadata"], active,
            )


if __name__ == "__main__":
    unittest.main()
