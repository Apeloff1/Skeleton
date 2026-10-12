"""Executable native physical encounter games from signed original genres."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from zipfile import ZipFile
from hashlib import sha256
import json
import unittest

from skeleton.ai.game_builder.advanced_godot_export import (
    AdvancedGodotExportError,archive_advanced_godot_package,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.system_editors import make_editor_document
from skeleton.ai.game_builder.advanced_physics_interop import (
    rehearse_physics_encounter,verify_physics_encounter,
)
from skeleton.ai.game_builder.advanced_physics_interop_godot import (
    SCHEMA,SOURCE_CHECK,render_interop_godot_package,
)


class SourceBoundNativeEncounterTests(unittest.TestCase):
    def original(self,editor,settings=None,commands=(),seed=1):
        scene=make_advanced_scene(editor,settings,seed=seed)
        session=run_advanced_session(editor,settings,commands,
                                      seed=seed,scene=scene)
        self.assertTrue(verify_advanced_session(session,settings))
        interop=rehearse_physics_encounter(session,settings)
        self.assertTrue(verify_physics_encounter(interop,session,settings))
        return session,interop

    def test_three_real_original_genre_physics_games_export(self):
        for editor in ("platformer","racing","sandbox"):
            with self.subTest(editor=editor):
                origin,physics=self.original(editor,seed=1)
                package=render_interop_godot_package(
                    physics,origin,authorized=True)
                self.assertEqual(package.manifest["native_editor"],"physics")
                self.assertEqual(package.manifest["source_editor"],editor)
                self.assertFalse(package.manifest["whole_original_genre_native"])
                self.assertFalse(package.manifest["godot_executed"])
                self.assertFalse(package.manifest["publish_approved"])
                src=json.loads(package.files["godot/origin.json"])
                assert src["schema"]==SCHEMA
                self.assertEqual(src["source_scene_digest"],origin["scene"]["digest"])
                self.assertEqual(src["original_authored_scene"],origin["scene"])
                self.assertEqual(src["original_source_settings"],
                                 make_editor_document(editor)["settings"])
                self.assertEqual(src["physics_session_digest"],
                                 physics["physics_session"]["digest"])
                self.assertEqual(src["actual_fixture_impacts"],
                                 physics["observed_fixture_impacts"])
                self.assertTrue(src["physical_witnesses"])
                game=json.loads(package.files["godot/game.json"])
                self.assertEqual(game["interop"]["source_editor"],editor)
                self.assertEqual(game["scene"]["layout"]["fixtures"],
                                 physics["physics_scene"]["layout"]["fixtures"])
                self.assertIn(SOURCE_CHECK.strip(),
                              package.files["godot/scripts/main.gd"].decode("utf-8"))
                self.assertTrue(package.files["godot/proof.json"])
                self.assertIn(b"verify-physics",package.files["README.md"])
                self.assertEqual(package.files,
                  render_interop_godot_package(
                    physics,origin,authorized=True).files)

    def test_native_genre_lane_avoidance_preserves_source_collision_masks(self):
        cfg={"track_length":80,"laps":2}
        origin,physics=self.original("racing",cfg,("steer_right",),seed=0)
        pack=render_interop_godot_package(physics,origin,cfg,authorized=True)
        src=json.loads(pack.files["godot/origin.json"])
        self.assertEqual(src["physical_witnesses"][0]["layer"],2)
        self.assertEqual(src["actual_fixture_impacts"],0)
        game=json.loads(pack.files["godot/game.json"])
        self.assertEqual(game["scene"]["layout"]["bodies"][0]["mask"],1)

    def test_deterministic_safe_archive_and_full_release_hashes(self):
        origin,proof=self.original("platformer")
        pack=render_interop_godot_package(proof,origin,authorized=True)
        self.assertEqual(set(pack.files),
                         set(pack.manifest["files"])|{"release.json"})
        for name,digest in pack.manifest["files"].items():
            self.assertEqual(sha256(pack.files[name]).hexdigest(),digest)
        archive=archive_advanced_godot_package(pack)
        with ZipFile(BytesIO(archive)) as z:
            self.assertIn("original-godot-physics/godot/origin.json",z.namelist())
            self.assertIn("original-godot-physics/godot/scripts/main.gd",z.namelist())

    def test_source_and_interop_tampering_fail_closed(self):
        source,proof=self.original("platformer")
        with self.assertRaises(PermissionError):
            render_interop_godot_package(proof,source,authorized=False)
        for changer in (
            lambda p:p["witnesses"][0].update(source_id=9999),
            lambda p:p.update(observed_fixture_impacts=0),
            lambda p:p["physics_session"]["state"].update(contacts=999),
        ):
            fake=deepcopy(proof)
            changer(fake)
            with self.assertRaises(AdvancedGodotExportError):
                render_interop_godot_package(fake,source,authorized=True)
        altered=deepcopy(source);altered["state"]["health"]=999
        with self.assertRaises(AdvancedGodotExportError):
            render_interop_godot_package(proof,altered,authorized=True)

    def test_game_bindings_explicitly_reject_unsourced_runtime_promotion(self):
        source,proof=self.original("sandbox",seed=4)
        package=render_interop_godot_package(proof,source,authorized=True)
        game=json.loads(package.files["godot/game.json"])
        src=json.loads(package.files["godot/origin.json"])
        self.assertEqual(game["interop"]["source_scene_digest"],
                         src["source_scene_digest"])
        self.assertFalse(src["auto_release"])
        self.assertFalse(src["hardware_certified"])
        self.assertFalse(src["linked_game_result_included"])
        self.assertFalse(src["whole_original_genre_native"])
        self.assertIn(b"source custody mismatch",
                      package.files["godot/scripts/main.gd"])


if __name__=="__main__":
    unittest.main()
