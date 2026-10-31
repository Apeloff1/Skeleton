"""Adversarial tests for original NPC sprites attached to real Godot actors."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_creator_source import CreatorProjectSourceStore
from skeleton.testing.test_jeeves_studio_sprite_forge import (
    original_record, original_sprite,
)

from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCRIPT
from skeleton.jeeves.ai.studio_sprite_npc_binding import (
    NpcSpriteBindingError, _npc_cast_names,
    preflight_original_npc_sprite_graph,
    authored_npc_sprite_bindings, bind_npc_sprites_to_expedition_script,
    verify_native_npc_binding_script,
)


def cast(*names: str) -> dict[str, str]:
    return {"game/frontier/npcs.json": json.dumps({
        "schema": "skeleton.game.original_npc_cast.v1",
        "cast": [{"design": {"npc_id": name}} for name in names],
    })}


def sprite(asset="sera-idle"):
    return {
        "asset_id": asset, "source_record_id": "sprite-1",
        "png_sha256": "a" * 64,
        "godot_spriteframes_resource_sha256": "b" * 64,
        "animation_names": ["idle", "walk", "climb"],
    }


def authored(npc_id="captain-sera", asset="sera-idle", animation="idle",
             dependencies=None):
    return {
        "scene-1": {
            "record_id": "scene-1", "facet": "scene_forge",
            "depends_on": dependencies if dependencies is not None else ["sprite-1"],
            "document": {
                "kind": "sprite_npc_binding", "npc_id": npc_id,
                "asset_id": asset, "animation": animation,
                "pixel_size": 0.025, "vertical_offset_m": 0.9,
                "billboard": True, "hide_capsule": True,
            },
        }
    }


class OriginalNpcSpriteBindingTests(unittest.TestCase):
    def original(self):
        return authored_npc_sprite_bindings(
            authored(), [sprite()], cast("captain-sera", "villager-2"),
        )

    def test_real_npc_cast_identity_is_exact(self):
        self.assertEqual(_npc_cast_names(cast("captain-sera", "villager-2")),
                         {"captain-sera", "villager-2"})

    def test_authored_npc_dependency_and_animation_compile(self):
        output = self.original()
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["source_record_id"], "scene-1")
        self.assertEqual(output[0]["sprite_source_record_id"], "sprite-1")
        self.assertEqual(output[0]["npc_id"], "captain-sera")
        self.assertEqual(output[0]["animation"], "idle")
        self.assertFalse(output[0]["native_npc_sprite_render_observed"])
        self.assertEqual(len(output[0]["receipt_sha256"]), 64)

    def test_compiled_npc_is_parented_to_moving_world_marker(self):
        compiled = bind_npc_sprites_to_expedition_script(
            _GODOT_SCRIPT, self.original(),
        )
        self.assertIn("npc.add_child(jeeves_npc_sprite)", compiled)
        self.assertIn('jeeves_npc_sprite.name = "OriginalAuthoredNPCSprite"',
                      compiled)
        self.assertIn("npc.mesh = null", compiled)
        self.assertIn('npc_markers[str(profile.get("npc_id", ""))] = npc',
                      compiled)
        self.assertIn("var jeeves_npc_id", compiled)
        self.assertIn("AnimatedSprite3D.new()", compiled)
        self.assertIn('res://game/frontier/sprites/', compiled)
        self.assertNotIn("if jeeves_npc_sprite.visible", compiled)

    def test_multiple_distinct_npcs_compile_in_canonical_order(self):
        source = authored()
        source["second-binding"] = {
            "record_id": "second-binding", "facet": "scene_forge",
            "depends_on": ["sprite-1"],
            "document": {
                **source["scene-1"]["document"],
                "npc_id": "villager-2",
                "animation": "walk",
                "billboard": False,
            },
        }
        selected = authored_npc_sprite_bindings(
            source, [sprite()], cast("villager-2", "captain-sera"),
        )
        self.assertEqual([s["npc_id"] for s in selected],
                         ["captain-sera", "villager-2"])
        game_script = bind_npc_sprites_to_expedition_script(
            _GODOT_SCRIPT, selected,
        )
        self.assertIn('"villager-2": {"asset":', game_script)
        self.assertIn('BaseMaterial3D.BILLBOARD_DISABLED', game_script)
        self.assertEqual(game_script.count("npc.add_child(jeeves_npc_sprite)"), 1)

    def test_repeated_compilation_is_byte_identical_and_provable(self):
        selected = self.original()
        first = bind_npc_sprites_to_expedition_script(
            _GODOT_SCRIPT, selected,
        )
        second = bind_npc_sprites_to_expedition_script(
            _GODOT_SCRIPT, selected,
        )
        self.assertEqual(first, second)
        receipt = verify_native_npc_binding_script(
            _GODOT_SCRIPT, first, selected,
        )
        self.assertEqual(receipt["npc_bound_count"], 1)
        self.assertTrue(receipt["exact_engine_source_reproduction"])
        self.assertFalse(receipt["native_npc_visual_render_verified"])

    def test_lost_original_dependency_is_rejected(self):
        with self.assertRaisesRegex(NpcSpriteBindingError, "dependency"):
            authored_npc_sprite_bindings(
                authored(dependencies=[]), [sprite()], cast("captain-sera"),
            )

    def test_made_up_world_character_is_not_created(self):
        with self.assertRaisesRegex(NpcSpriteBindingError, "absent"):
            authored_npc_sprite_bindings(
                authored(npc_id="invisible-guest"), [sprite()], cast("captain-sera"),
            )

    def test_made_up_sprite_is_not_silently_generated(self):
        with self.assertRaisesRegex(NpcSpriteBindingError, "sprite or animation"):
            authored_npc_sprite_bindings(
                authored(asset="unknown"), [sprite()], cast("captain-sera"),
            )

    def test_absent_animation_fails_closed(self):
        with self.assertRaisesRegex(NpcSpriteBindingError, "sprite or animation"):
            authored_npc_sprite_bindings(
                authored(animation="missing"), [sprite()], cast("captain-sera"),
            )

    def test_double_binding_one_character_cannot_overwrite(self):
        source = authored()
        source["competing"] = deepcopy(source["scene-1"])
        source["competing"]["record_id"] = "competing"
        with self.assertRaisesRegex(NpcSpriteBindingError, "multiple original"):
            authored_npc_sprite_bindings(
                source, [sprite()], cast("captain-sera"),
            )

    def test_unreviewed_sprite_visual_policy_is_rejected(self):
        source = authored()
        source["scene-1"]["document"]["billboard"] = 1
        with self.assertRaisesRegex(NpcSpriteBindingError, "boolean"):
            authored_npc_sprite_bindings(
                source, [sprite()], cast("captain-sera"),
            )

    def test_invalid_npc_world_cast_rejects_duplicate_identity(self):
        with self.assertRaisesRegex(NpcSpriteBindingError, "ambiguous"):
            _npc_cast_names(cast("captain-sera", "captain-sera"))

    def test_npc_source_rejects_extra_unsafe_fields(self):
        source = authored()
        source["scene-1"]["document"]["script_override"] = "print('hack')"
        with self.assertRaisesRegex(NpcSpriteBindingError, "complete"):
            authored_npc_sprite_bindings(
                source, [sprite()], cast("captain-sera"),
            )

    def test_tampered_native_script_receipt_fails_replay(self):
        selected = self.original()
        script = bind_npc_sprites_to_expedition_script(
            _GODOT_SCRIPT, selected,
        )
        altered = script.replace("npc.mesh = null", "npc.mesh = CapsuleMesh.new()")
        with self.assertRaisesRegex(NpcSpriteBindingError, "changed"):
            verify_native_npc_binding_script(
                _GODOT_SCRIPT, altered, selected,
            )

    def test_tampered_bound_receipt_is_not_embedded(self):
        selected = self.original()
        selected[0]["pixel_size"] = 0.25
        with self.assertRaisesRegex(NpcSpriteBindingError, "modified"):
            bind_npc_sprites_to_expedition_script(
                _GODOT_SCRIPT, selected,
            )

    def test_unbound_project_keeps_original_godot_script_intact(self):
        self.assertEqual(
            bind_npc_sprites_to_expedition_script(_GODOT_SCRIPT, []),
            _GODOT_SCRIPT,
        )


class NpcSpriteGraphPreflightTests(unittest.TestCase):
    def records(self):
        game_art = original_record()
        source = authored(
            asset="hero-idle", dependencies=["hero-source"],
        )
        return {"hero-source": game_art, **source}

    def test_real_original_sprite_deps_are_valid_before_commit(self):
        report = preflight_original_npc_sprite_graph(self.records())
        self.assertEqual(report["checked_record_ids"], ["scene-1"])
        self.assertTrue(report["sprite_dependencies_valid"])
        self.assertFalse(report["world_npc_identity_verified"])

    def test_edits_cannot_leave_dangling_sprite_animation(self):
        sources = self.records()
        sources["scene-1"]["document"]["animation"] = "unknown"
        with self.assertRaisesRegex(NpcSpriteBindingError, "animation missing"):
            preflight_original_npc_sprite_graph(sources)

    def test_edits_cannot_remove_original_asset_dependency(self):
        sources = self.records()
        sources["scene-1"]["depends_on"] = []
        with self.assertRaisesRegex(NpcSpriteBindingError, "depend"):
            preflight_original_npc_sprite_graph(sources)

    def test_edits_cannot_change_npc_sprite_with_invalid_source_sha(self):
        sources = self.records()
        sources["hero-source"]["document"]["width"] = 6
        with self.assertRaises(ValueError):
            preflight_original_npc_sprite_graph(sources)

    def test_duplicate_original_npc_identity_is_refused_at_commit_boundary(self):
        sources = self.records()
        sources["different"] = deepcopy(sources["scene-1"])
        sources["different"]["record_id"] = "different"
        with self.assertRaisesRegex(NpcSpriteBindingError, "authored twice"):
            preflight_original_npc_sprite_graph(sources)

    def test_durable_edit_preserves_original_animation_when_npc_depends_on_it(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with CreatorProjectSourceStore(
                root / "game.sqlite", project_id="original-game",
                export_root=root,
            ) as store:
                store.create(build_creator_command(
                    "create", project_id="original-game",
                    payload={"intent": {
                        "record_id": "hero-source", "facet": "sprite_forge",
                        "document": original_sprite(), "depends_on": [],
                    }},
                ))
                store.create(build_creator_command(
                    "create", project_id="original-game",
                    payload={"intent": {
                        "record_id": "scene-1", "facet": "scene_forge",
                        "document": self.records()["scene-1"]["document"],
                        "depends_on": ["hero-source"],
                    }},
                ))
                before = store.snapshot()["head_sha256"]
                with self.assertRaisesRegex(NpcSpriteBindingError, "animation missing"):
                    store.edit(build_creator_command(
                        "edit", project_id="original-game",
                        payload={
                            "target_id": "hero-source", "expected_revision": 1,
                            "patch": {
                                "set": {"animations": [{
                                    "name": "walk",
                                    "frame_ids": ["idle-0"],
                                    "loop": True,
                                }]},
                                "remove": [],
                            },
                        },
                    ))
                self.assertEqual(store.snapshot()["head_sha256"], before)
                self.assertEqual(store.snapshot()["source_count"], 2)


if __name__ == "__main__":
    unittest.main()
