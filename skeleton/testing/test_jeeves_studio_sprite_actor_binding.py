"""Safety and end-to-end source invariants for the original Godot player avatar.

This suite does not spoof Godot success. It verifies that a SOURCE-VERIFIED
sprite binds exactly one authored animation to the real game actor, scripts
cannot be injected, and native replay refuses missing executables or changed
game files instead of claiming runtime completion.
"""
from __future__ import annotations

import unittest

from skeleton.jeeves.ai.studio_sprite_actor_binding import (
    SpriteBindingError, binding_from_source,
    bind_sprite_to_expedition_script, verify_actor_sprite_binding,
)
from skeleton.jeeves.ai.studio_sprite_bound_native_runner import (
    SpriteBoundNativeError, run_sprite_bound_native_expedition,
)
from skeleton.jeeves.ai.studio_sprite_forge import compile_authored_sprite
from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCRIPT
from skeleton.testing.test_jeeves_studio_sprite_forge import original_record


def binding_source(*, asset="hero-idle", animation="idle", deps=None) -> dict:
    return {
        "record_id": "hero-binding",
        "facet": "scene_forge",
        "depends_on": ["hero-source"] if deps is None else deps,
        "document": {
            "kind": "sprite_actor_binding",
            "target": "player_actor",
            "asset_id": asset,
            "animation": animation,
            "pixel_size": 0.025,
            "vertical_offset_m": 1.5,
            "billboard": True,
            "hide_capsule": True,
        },
    }


def source_with_avatar(binding=None):
    record = original_record()
    compiled = compile_authored_sprite(record)
    metadata = compiled["metadata"]
    asset = {
        "asset_id": metadata["asset_id"],
        "source_record_id": metadata["record_id"],
        "animation_names": [state["name"] for state in metadata["animations"]],
        "png_sha256": metadata["png_sha256"],
        "godot_spriteframes_resource_sha256": metadata["receipt_sha256"],
    }
    return {
        "hero-binding": binding_source() if binding is None else binding,
    }, [asset]


class OriginalPlayerSpriteBindingTests(unittest.TestCase):
    def test_original_sprite_binds_actual_player_and_preserves_navigation(self):
        records, sprites = source_with_avatar()
        proof = binding_from_source(records, sprites)
        self.assertEqual(proof["target"], "player_actor")
        script = bind_sprite_to_expedition_script(_GODOT_SCRIPT, proof)
        self.assertIn("jeeves_avatar := AnimatedSprite3D.new()", script)
        self.assertIn("actor.add_child(jeeves_avatar)", script)
        self.assertIn("actor.mesh = null", script)
        self.assertIn("    _place_actor()", script)
        self.assertIn('jeeves_avatar.animation = &"idle"', script)
        self.assertEqual(script.count("    _place_actor()"), 2)
        self.assertTrue(verify_actor_sprite_binding(
            _GODOT_SCRIPT, script, proof,
        )["source_reproduction_verified"])

    def test_actor_has_no_unreviewed_sprite_by_default(self):
        self.assertIsNone(binding_from_source({}, []))
        self.assertIsNone(binding_from_source({
            "hero-unrelated": {
                "document": {"kind": "quest", "title": "nothing bound"},
            },
        }, []))

    def test_missing_referenced_png_refuses_binding(self):
        records, sprites = source_with_avatar()
        sprites.clear()
        with self.assertRaisesRegex(SpriteBindingError, "unavailable"):
            binding_from_source(records, sprites)

    def test_sprite_binding_requires_canonical_source_dependency(self):
        records, sprites = source_with_avatar(binding_source(deps=["map-1"]))
        with self.assertRaisesRegex(SpriteBindingError, "depend"):
            binding_from_source(records, sprites)

    def test_duplicate_avatar_sources_cannot_fight_for_actor(self):
        records, sprites = source_with_avatar()
        second = binding_source()
        second["record_id"] = "other-binding"
        records["other-binding"] = second
        with self.assertRaisesRegex(SpriteBindingError, "multiple"):
            binding_from_source(records, sprites)

    def test_unknown_animation_cannot_start_hidden_fallback(self):
        records, sprites = source_with_avatar(binding_source(animation="unknown"))
        with self.assertRaisesRegex(SpriteBindingError, "animation"):
            binding_from_source(records, sprites)

    def test_foreign_sprite_target_is_denied(self):
        source = binding_source()
        source["document"]["target"] = "npc_boss"
        records, sprites = source_with_avatar(source)
        with self.assertRaisesRegex(SpriteBindingError, "player actor"):
            binding_from_source(records, sprites)

    def test_source_supplied_script_payload_cannot_run(self):
        source = binding_source()
        source["document"]["unsafe_code"] = "OS.execute('rm -rf .')"
        records, sprites = source_with_avatar(source)
        with self.assertRaisesRegex(SpriteBindingError, "exact"):
            binding_from_source(records, sprites)

    def test_script_injection_is_denied_even_if_metadata_hash_recomputed(self):
        source = binding_source()
        source["document"]["animation"] = "idle\";\nquit()"
        records, sprites = source_with_avatar(source)
        with self.assertRaisesRegex(SpriteBindingError, "unsafe"):
            binding_from_source(records, sprites)

    def test_empty_billboard_policy_invalid(self):
        source = binding_source()
        source["document"]["billboard"] = "no"
        records, sprites = source_with_avatar(source)
        with self.assertRaisesRegex(SpriteBindingError, "boolean"):
            binding_from_source(records, sprites)

    def test_nan_pixel_scale_is_rejected(self):
        source = binding_source()
        source["document"]["pixel_size"] = float("nan")
        records, sprites = source_with_avatar(source)
        with self.assertRaisesRegex(SpriteBindingError, "bounded"):
            binding_from_source(records, sprites)

    def test_pixel_size_and_vertical_offsets_strictly_bounded(self):
        for name, value in [("pixel_size", 0), ("vertical_offset_m", 1000)]:
            source = binding_source()
            source["document"][name] = value
            records, sprites = source_with_avatar(source)
            with self.assertRaises(SpriteBindingError):
                binding_from_source(records, sprites)

    def test_original_game_script_never_substituted_if_anchor_moves(self):
        records, sprites = source_with_avatar()
        binding = binding_from_source(records, sprites)
        with self.assertRaisesRegex(SpriteBindingError, "anchor differs"):
            bind_sprite_to_expedition_script(
                _GODOT_SCRIPT.replace("    add_child(actor)\n    _place_actor()",
                                       "    add_child(actor)"),
                binding,
            )

    def test_native_player_script_tampering_is_detected(self):
        records, sprites = source_with_avatar()
        binding = binding_from_source(records, sprites)
        compiled = bind_sprite_to_expedition_script(_GODOT_SCRIPT, binding)
        self.assertNotEqual(_GODOT_SCRIPT, compiled)
        with self.assertRaisesRegex(SpriteBindingError, "differs"):
            verify_actor_sprite_binding(
                _GODOT_SCRIPT, compiled.replace(
                    "jeeves_avatar.play()", "jeeves_avatar.stop()",
                ), binding,
            )

    def test_native_runtime_requires_installed_engine_not_mock_result(self):
        with self.assertRaises(SpriteBoundNativeError):
            run_sprite_bound_native_expedition(
                {}, None, None,
                godot_executable="/absent/godot4",
            )


if __name__ == "__main__":
    unittest.main()
