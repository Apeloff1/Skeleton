"""Adversarial frame-cue and live Godot signal source regression suite."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.creator.command_surface import build_creator_command
from skeleton.jeeves.ai.studio_creator_source import CreatorProjectSourceStore
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_sprite_frame_cues import (
    SpriteCueError, compile_frame_cues, emit_godot_frame_cue_files,
    verify_frame_cues, verify_godot_frame_cue_files,
)
from skeleton.jeeves.ai.studio_sprite_forge import compile_authored_sprite
from skeleton.jeeves.ai.studio_sprite_native_import import (
    NativeSpriteImportError, _expected_original_frame_cue_observations,
    _GD_CHECK,
)
from skeleton.jeeves.ai.studio_sprite_verify import (
    SpriteVerificationError, verify_published_sprite,
)
from skeleton.testing.test_jeeves_studio_sprite_forge import original_record


def original_with_cues() -> dict:
    record = original_record()
    record["document"]["cues"] = [
        {"animation": "idle", "frame_index": 0,
         "event_id": "step-left", "category": "footstep"},
        {"animation": "idle", "frame_index": 1,
         "event_id": "cloth-swish", "category": "sound"},
        {"animation": "pose", "frame_index": 0,
         "event_id": "action-marker", "category": "marker"},
    ]
    return reseal(record)


def reseal(record: dict) -> dict:
    record["source_sha256"] = digest([
        record["record_id"], record["facet"], record["revision"],
        record["document"], record["depends_on"],
    ])
    return record


class SpriteFrameCueTests(unittest.TestCase):
    def test_frame_cues_compile_as_verified_source_not_effects(self):
        record = original_with_cues()
        artifact = compile_authored_sprite(record)
        cues = artifact["metadata"]["frame_cues"]
        self.assertEqual(cues["cue_count"], 3)
        self.assertEqual(cues["by_animation_frame"]["idle:0"],
                         [["footstep", "step-left"]])
        self.assertEqual(cues["by_animation_frame"]["idle:1"],
                         [["sound", "cloth-swish"]])
        self.assertEqual(cues["cues"][0]["frame_id"], "idle-0")
        self.assertTrue(cues["runtime_signal_only"])
        self.assertFalse(cues["audio_and_vfx_effects_executed"])
        self.assertEqual(verify_frame_cues(
            record["document"], artifact["metadata"],
        ), cues)
        self.assertEqual(
            artifact["independent_pixel_replay"]["authored_frame_cues_verified"], 3,
        )

    def test_godot_signal_script_contains_only_whitelisted_static_emit(self):
        meta = compile_authored_sprite(original_with_cues())["metadata"]
        files = emit_godot_frame_cue_files(meta)
        self.assertEqual(set(files), {
            "game/frontier/sprites/hero-idle.cues.json",
            "game/frontier/sprites/hero-idle.cues.gd",
        })
        script = files["game/frontier/sprites/hero-idle.cues.gd"]
        self.assertIn("extends AnimatedSprite3D", script)
        self.assertIn("frame_changed.connect(_publish_frame_cues)", script)
        self.assertIn("cue_fired.emit(", script)
        self.assertNotIn("get_tree()", script)
        self.assertNotIn("FileAccess", script)
        self.assertNotIn("OS.execute", script)
        proof = verify_godot_frame_cue_files(meta, files)
        self.assertTrue(proof["signal_source_reproduced"])
        self.assertFalse(proof["audio_or_vfx_execution_verified"])

    def test_godot_cue_script_is_reproducible(self):
        source = compile_authored_sprite(original_with_cues())["metadata"]
        self.assertEqual(emit_godot_frame_cue_files(source),
                         emit_godot_frame_cue_files(source))

    def test_invalid_frame_refuses_to_guess_event_position(self):
        record = original_with_cues()
        record["document"]["cues"][0]["frame_index"] = 900
        with self.assertRaisesRegex(SpriteCueError, "not authored"):
            compile_authored_sprite(reseal(record))

    def test_missing_animation_refuses_to_emit_signals(self):
        record = original_with_cues()
        record["document"]["cues"][0]["animation"] = "never-created"
        with self.assertRaisesRegex(SpriteCueError, "not authored"):
            compile_authored_sprite(reseal(record))

    def test_duplicate_event_at_same_frame_is_rejected(self):
        record = original_with_cues()
        record["document"]["cues"].append(
            deepcopy(record["document"]["cues"][0])
        )
        with self.assertRaisesRegex(SpriteCueError, "duplicate cue"):
            compile_authored_sprite(reseal(record))

    def test_unsupported_event_is_never_code_execution(self):
        record = original_with_cues()
        record["document"]["cues"][0]["category"] = "execute_script"
        with self.assertRaisesRegex(SpriteCueError, "non-executing"):
            compile_authored_sprite(reseal(record))

    def test_unsafe_event_id_cannot_escape_godot_script(self):
        record = original_with_cues()
        record["document"]["cues"][0]["event_id"] = 'x\"); OS.execute("hack"'
        with self.assertRaisesRegex(SpriteCueError, "portable"):
            compile_authored_sprite(reseal(record))

    def test_cues_reject_boolean_and_negative_frame_index(self):
        for bad in (True, -1, 1.0):
            record = original_with_cues()
            record["document"]["cues"][0]["frame_index"] = bad
            with self.assertRaisesRegex(SpriteCueError, "not authored"):
                compile_authored_sprite(reseal(record))

    def test_tampered_cue_receipt_rejected_even_with_metadata_reseal(self):
        artifact = compile_authored_sprite(original_with_cues())
        metadata = deepcopy(artifact["metadata"])
        metadata["frame_cues"]["by_animation_frame"]["idle:0"] = [
            ["attack", "step-left"]
        ]
        metadata["frame_cues"]["receipt_sha256"] = digest({
            key: value for key, value in metadata["frame_cues"].items()
            if key != "receipt_sha256"
        })
        metadata["receipt_sha256"] = digest({
            key: value for key, value in metadata.items()
            if key != "receipt_sha256"
        })
        with self.assertRaisesRegex(SpriteVerificationError, "cue markers"):
            verify_published_sprite(artifact["png"], metadata)

    def test_tampered_godot_script_is_refused(self):
        meta = compile_authored_sprite(original_with_cues())["metadata"]
        generated = emit_godot_frame_cue_files(meta)
        path = "game/frontier/sprites/hero-idle.cues.gd"
        generated[path] = generated[path].replace(
            "cue_fired.emit(", "get_tree().quit(); cue_fired.emit(",
        )
        with self.assertRaisesRegex(SpriteCueError, "signal source differs"):
            verify_godot_frame_cue_files(meta, generated)

    def test_explicit_null_cues_are_not_silent_empty_source(self):
        record = original_record()
        record["document"]["cues"] = None
        with self.assertRaisesRegex(SpriteCueError, "1..128"):
            compile_authored_sprite(reseal(record))

    def test_real_engine_cue_probe_has_exact_independent_expectations(self):
        artifact = compile_authored_sprite(original_with_cues())
        keys, expected = _expected_original_frame_cue_observations(
            artifact["metadata"],
        )
        self.assertEqual(keys, ["idle:0", "idle:1", "pose:0"])
        self.assertEqual(expected, [
            ["step-left", "footstep", "idle", 0],
            ["cloth-swish", "sound", "idle", 1],
            ["action-marker", "marker", "pose", 0],
        ])
        self.assertIn('cue_script := load(', _GD_CHECK)
        self.assertIn('cue_fired', _GD_CHECK)
        self.assertIn('observed_cues != expected["cue_observations"]', _GD_CHECK)

    def test_real_engine_probe_is_inert_for_legacy_sprite(self):
        legacy = compile_authored_sprite(original_record())
        self.assertEqual(
            _expected_original_frame_cue_observations(legacy["metadata"]),
            ([], []),
        )

    def test_native_probe_rejects_fake_cue_timing_with_rehashed_claim(self):
        artifact = compile_authored_sprite(original_with_cues())
        forged = deepcopy(artifact["metadata"])
        forged["frame_cues"]["cues"][0]["frame_id"] = "wrong"
        forged["frame_cues"]["receipt_sha256"] = digest({
            key: value for key, value in forged["frame_cues"].items()
            if key != "receipt_sha256"
        })
        with self.assertRaisesRegex(NativeSpriteImportError, "differ"):
            _expected_original_frame_cue_observations(forged)

    def test_native_probe_rejects_malformed_missing_source_cues(self):
        artifact = compile_authored_sprite(original_with_cues())
        forged = deepcopy(artifact["metadata"])
        forged["frame_cues"]["cues"][0]["event_id"] = []
        with self.assertRaises(NativeSpriteImportError):
            _expected_original_frame_cue_observations(forged)

    def test_legacy_sprite_remains_cue_free(self):
        artifact = compile_authored_sprite(original_record())
        self.assertIsNone(artifact["metadata"]["frame_cues"])
        self.assertEqual(emit_godot_frame_cue_files(artifact["metadata"]), {})

    def test_invalid_source_cue_is_rejected_before_sqlite_mutation(self):
        record = original_with_cues()
        record["document"]["cues"][0]["category"] = "shell"
        with TemporaryDirectory() as folder:
            root = Path(folder)
            root.joinpath("exports").mkdir()
            with CreatorProjectSourceStore(
                root / "source.sqlite", project_id="sprite-cues",
                export_root=root / "exports",
            ) as owner:
                with self.assertRaises(SpriteCueError):
                    owner.create(build_creator_command(
                        "create", project_id="sprite-cues",
                        payload={"intent": {
                            "record_id": "hero-source", "facet": "sprite_forge",
                            "document": record["document"], "depends_on": [],
                        }},
                    ))
                self.assertEqual(owner.snapshot()["source_count"], 0)


if __name__ == "__main__":
    unittest.main()
