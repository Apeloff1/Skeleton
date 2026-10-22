"""Original eight-way player-sprite directional animation regressions.

Exercises actual persisted Jeeves records, vetted pixel frames, native Godot
script output, content-addressed ZIP verification and fail-closed source edits.
No test pretends that having GDScript proves a running renderer.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
import zipfile

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_sprite_direction import (
    FACING, PLACE_ANCHOR, SpriteDirectionError,
    compile_eight_way_actor_facing, validate_directional_animations,
    verify_eight_way_actor_facing,
)
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCRIPT
from skeleton.testing.test_jeeves_studio_frontier_source_compile import (
    RealGodotSourceBuildTests,
)


def approved_binding(*, directions: dict[str, str]) -> dict:
    body = {
        "schema_version": "skeleton.jeeves.player_sprite_binding.v1",
        "record_id": "avatar-heading", "target": "player_actor",
        "asset_id": "hero-idle", "animation": "idle",
        "directional_animations": directions,
    }
    body["receipt_sha256"] = digest(body)
    return body


class TestJeevesSpriteDirectionCompiler(unittest.TestCase):
    def test_cardinal_and_diagonal_names_follow_real_world_axes(self):
        self.assertEqual(FACING, (
            "north", "north_east", "east", "south_east",
            "south", "south_west", "west", "north_west",
        ))

    def test_requires_real_original_animation_not_generated_defaults(self):
        with self.assertRaisesRegex(SpriteDirectionError, "uncompiled"):
            validate_directional_animations(
                {"north": "missing"}, available=["idle"], default="idle",
            )

    def test_rejects_unsafe_direction_identifiers(self):
        with self.assertRaisesRegex(SpriteDirectionError, "uncompiled"):
            validate_directional_animations(
                {"../path": "idle"}, available=["idle"], default="idle",
            )

    def test_validates_complete_eight_direction_catalogue(self):
        headings = {direction: "idle" for direction in FACING}
        result = validate_directional_animations(
            headings, available=["idle"], default="idle",
        )
        self.assertEqual(result, dict(sorted(headings.items())))

    def test_north_is_negative_z_and_east_is_positive_x(self):
        original = _GODOT_SCRIPT
        bound = compile_eight_way_actor_facing(
            original, approved_binding(directions={
                "north": "idle", "east": "walk",
            }),
        )
        self.assertIn("atan2(jeeves_compass_delta.x, -jeeves_compass_delta.z)", bound)
        self.assertIn('"north": "idle"', bound)
        self.assertIn('"east": "walk"', bound)
        self.assertIn('jeeves_heading_avatar.play(jeeves_animation_name)', bound)
        self.assertIn("jeeves_compass_delta.y = 0.0", bound)
        self.assertEqual(bound.count("func _place_actor() -> void:"), 1)
        self.assertTrue(verify_eight_way_actor_facing(
            original, bound, approved_binding(directions={
                "north": "idle", "east": "walk",
            }),
        )["vertical_movement_affects_facing"] is False)

    def test_does_not_modify_route_permissions_or_spend(self):
        binding = approved_binding(directions={"south": "glide"})
        script = compile_eight_way_actor_facing(_GODOT_SCRIPT, binding)
        self.assertEqual(
            script.count('stamina -= int(costs["stamina"])'),
            _GODOT_SCRIPT.count('stamina -= int(costs["stamina"])'),
        )
        self.assertEqual(script.count("func _can_travel("),
                         _GODOT_SCRIPT.count("func _can_travel("))

    def test_tampered_script_cannot_pass_original_receipt(self):
        original = _GODOT_SCRIPT
        binding = approved_binding(directions={"north": "idle"})
        generated = compile_eight_way_actor_facing(original, binding)
        altered = generated.replace('"north": "idle"', '"north": "faked"')
        with self.assertRaisesRegex(SpriteDirectionError, "after compilation"):
            verify_eight_way_actor_facing(original, altered, binding)

    def test_invalid_source_claim_blocks_script_modification(self):
        binding = approved_binding(directions={"north": "idle"})
        binding["directional_animations"] = {"south": "walk"}
        with self.assertRaisesRegex(SpriteDirectionError, "receipt"):
            compile_eight_way_actor_facing(_GODOT_SCRIPT, binding)

    def test_unsupported_travel_anchor_refuses_source_compilation(self):
        binding = approved_binding(directions={"north": "idle"})
        without = _GODOT_SCRIPT.replace(PLACE_ANCHOR, "func _place_actor() -> void:")
        with self.assertRaisesRegex(SpriteDirectionError, "anchor"):
            compile_eight_way_actor_facing(without, binding)


class TestJeevesSpriteDirectionGame(unittest.TestCase):
    setUp = RealGodotSourceBuildTests.setUp
    create = RealGodotSourceBuildTests.create
    populate_3d = RealGodotSourceBuildTests.populate_3d
    export_godot = RealGodotSourceBuildTests.export_godot
    author_player_visual = RealGodotSourceBuildTests.author_player_visual

    def _author_compass(self, directions=None):
        self.populate_3d()
        self.author_player_visual(directional_map=(
            {"north": "idle", "east": "walk", "south": "glide"}
            if directions is None else directions
        ))

    def test_real_godot_archive_contains_bound_compass_and_sha_receipts(self):
        self._author_compass()
        exported = self.export_godot()
        with zipfile.ZipFile(self.export / exported["artifact_name"]) as bundle:
            script = bundle.read("game/frontier/expedition.gd").decode("utf-8")
            evidence = json.loads(bundle.read("jeeves_source_receipt.json"))
        self.assertIn("jeeves_compass_names: Array =", script)
        self.assertIn('var jeeves_current_heading', script)
        self.assertIn('actor.add_child(jeeves_avatar)', script)
        self.assertEqual(
            evidence["authored_player_avatar_binding"]["directional_animations"],
            {"east": "walk", "north": "idle", "south": "glide"},
        )
        self.assertTrue(evidence["native_player_eight_way_facing_compiled"])
        self.assertTrue(evidence["player_compass_godot_source_receipt"][
            "original_engine_source_sha256"
        ])
        self.assertFalse(evidence["player_compass_godot_source_receipt"][
            "engine_compass_observed"
        ])
        self.assertTrue(exported["disk_verification"][
            "all_emitted_file_hashes_verified"
        ])

    def test_nonexistent_compass_animation_is_rejected_before_sqlite_write(self):
        self.populate_3d()
        with self.assertRaisesRegex(SpriteDirectionError, "uncompiled"):
            self.author_player_visual(directional_map={"west": "not-created"})
        self.assertEqual(self.owner.snapshot()["source_count"], 5)
        self.assertFalse(any(self.export.iterdir()))

    def test_invalid_heading_refuses_original_scene_source(self):
        self.populate_3d()
        with self.assertRaisesRegex(SpriteDirectionError, "uncompiled"):
            self.author_player_visual(directional_map={"northwest": "walk"})
        self.assertEqual(self.owner.snapshot()["source_count"], 5)

    def test_source_edit_cannot_delete_current_compass_animation(self):
        self._author_compass()
        self.assertEqual(self.owner.snapshot()["source_count"], 6)
        with self.assertRaisesRegex(SpriteDirectionError, "uncompiled"):
            self.owner.edit(build_creator_command(
                "edit", project_id="new-game",
                payload={
                    "target_id": "hero-art", "expected_revision": 1,
                    "patch": {
                        "set": {"animations": [
                            {"name": "idle",
                             "frame_ids": ["first", "second"], "loop": True},
                        ]}, "remove": [],
                    },
                },
            ))
        self.assertEqual(self.owner._records["hero-art"]["revision"], 1)
        self.assertEqual(self.owner._records["hero-visual-binding"]["revision"], 1)
        self.assertFalse(any(self.export.iterdir()))

    def test_sprite_headings_are_explicitly_unexecuted_on_export(self):
        self._author_compass()
        result = self.export_godot()
        with zipfile.ZipFile(self.export / result["artifact_name"]) as bundle:
            proof = json.loads(bundle.read("jeeves_source_receipt.json"))
        self.assertFalse(proof["native_godot_playthrough_verified"])
        self.assertFalse(proof["native_sprite_scene_binding_verified"])
        self.assertTrue(proof["animated_sprite3d_player_script_compiled"])


if __name__ == "__main__":
    unittest.main()
