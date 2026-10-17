"""Jeeves studio source production uses real emitters and human CAS admission."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace, WorkspaceError
from skeleton.ai.game_builder.jeeves_app_runtime import (
    EMPTY_SHA, JeevesAppCapabilityError, dispatch_app_action,
)


class JeevesConsoleSourceStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = GameWorkspace.create(Path(self.tmp.name) / "studio", authorized=True)
        self.project = "originalconsole"
        self.workspace.create_project(self.project, "puzzle", authorized=True)
        self.initial_paths = sorted(row.path for row in self.workspace.files("current", self.project))
        self.intent = {
            "title": "Original Console Source",
            "subtitle": "One real input-driven game and its original graphic assets",
            "seed": 733,
            "width": 11,
            "height": 11,
            "levels": 1,
            "collectibles_per_level": 1,
            "hazards_per_level": 1,
            "starting_health": 4,
            "theme": "ocean",
        }

    def call(self, name, payload, *, authorized=True):
        return dispatch_app_action(
            self.workspace, self.project, name, payload, authorized=authorized,
        )

    def request(self, target="nintendo_game_boy", source_file="main.asm"):
        return {
            "intent": self.intent,
            "target": target,
            "source_platform": "bandai_wonderswan",
            "rights_evidence_sha256": sha256(b"original authorship evidence").hexdigest(),
            "creative_identity": ["original-characters", "independent-mechanics"],
            "style": "arcade",
            "contrast": "high",
            "animation_frames": 3,
            "source_file": source_file,
            "expected_sha256": EMPTY_SHA,
            "reason": "Stage original native source and verified indexed sprite pixels for review",
        }

    def test_catalog_has_genuine_emitters_and_conservative_authority(self):
        catalog = self.call("game.console.catalog", {}, authorized=False)["result"]
        self.assertEqual(len(catalog["targets"]), 5)
        self.assertTrue(catalog["source_art_embedded"])
        self.assertFalse(catalog["native_executable_compiled"])
        self.assertFalse(catalog["external_toolchain_invoked"])
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("game.console.catalog", {"shell": "run"}, authorized=False)

    def test_source_is_generated_and_human_approval_required(self):
        for target, source_file, marker in (
            ("nintendo_game_boy", "main.asm", "Tiles:"),
            ("nintendo_game_boy_color", "main.asm", "Tiles:"),
            ("nintendo_famicom", "main.s", ".segment"),
            ("sega_master_system", "game.asm", "org"),
            ("sega_game_gear", "game.c", "static"),
        ):
            with self.subTest(target=target):
                payload = self.request(target, source_file)
                with self.assertRaises(PermissionError):
                    self.call("game.console.source.stage", payload, authorized=False)
                result = self.call("game.console.source.stage", payload)["result"]
                self.assertTrue(result["actual_native_source_generated"])
                self.assertTrue(result["actual_sprite_pixels_embedded"])
                if target in ("nintendo_game_boy", "nintendo_game_boy_color",
                              "nintendo_famicom"):
                    self.assertTrue(result["native_animation_source_integrated"])
                    self.assertTrue(result["native_psg_audio_source_integrated"])
                    self.assertEqual(result["animation_frame_count"], 3)
                    self.assertEqual(result["native_animation_frame_delay"], 15)
                    self.assertEqual(len(result["native_psg_score_digest"]), 64)
                else:
                    self.assertFalse(result["native_animation_source_integrated"])
                    self.assertFalse(result["native_psg_audio_source_integrated"])
                    self.assertIsNone(result["native_psg_score_digest"])
                self.assertFalse(result["emulator_audio_executed"])
                self.assertFalse(result["native_pcm_sound_equivalence_claimed"])
                self.assertFalse(result["binary_compiled"])
                self.assertFalse(result["rights_independently_verified"])
                self.assertFalse(result["source_committed"])
                self.assertTrue(result["human_review_and_explicit_commit_required"])
                path = result["generated_source_file"]
                self.assertEqual(path, f"game/native/{target}/{source_file}")
                # New native source is still a proposal, never auto-committed.
                self.assertNotIn(path, [item.path for item in self.workspace.files("current", self.project)])
                committed = self.workspace.commit(
                    result["proposal_id"], human_approved=True, authorized=True,
                )
                self.assertTrue(committed["approved"])
                original = self.workspace.read("current", self.project, path)
                self.assertIn(marker, original["content"])
                self.assertEqual(committed["sha256"], result["generated_source_sha256"])
                self.assertEqual(original["version"]["sha256"], committed["sha256"])

    def test_operator_can_adjust_real_native_music_and_sprite_timing(self):
        request = {
            **self.request(), "animation_fps": 10, "music_density": 0,
        }
        output = self.call("game.console.source.stage", request)["result"]
        self.assertEqual(output["native_animation_frame_delay"], 6)
        self.assertTrue(output["native_animation_source_integrated"])
        self.assertFalse(output["native_psg_audio_source_integrated"])
        self.assertFalse(output["binary_compiled"])
        with self.assertRaises(ValueError):
            self.call("game.console.source.stage", {
                **request, "animation_fps": 0,
            })
        with self.assertRaises(ValueError):
            self.call("game.console.source.stage", {
                **request, "music_density": 5,
            })

    def test_nonexistent_target_wrong_source_and_invalid_authority_fail_closed(self):
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("game.console.source.stage",
                      self.request("nintendo_switch", "game.c"))
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("game.console.source.stage",
                      self.request("nintendo_famicom", "game.c"))
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("game.console.source.stage", {
                **self.request(), "source_platform": "path_traversal"
            })
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("game.console.source.stage", {
                **self.request(), "rights_evidence_sha256": "invalid"
            })
        with self.assertRaises(ValueError):
            self.call("game.console.source.stage", {
                **self.request(), "intent": {**self.intent, "width": 8}
            })
        with self.assertRaises(JeevesAppCapabilityError):
            self.call("game.console.source.stage", {
                **self.request(), "intent": {**self.intent, "levels": 8}
            })
        with self.assertRaises(ValueError):
            self.call("game.console.source.stage", {
                **self.request(), "creative_identity": []
            })
        self.assertEqual(
            sorted(row.path for row in self.workspace.files("current", self.project)),
            self.initial_paths,
        )

    def test_stale_source_revisions_do_not_overwrite_and_unauthorized_commit_denied(self):
        payload = self.request()
        result = self.call("game.console.source.stage", payload)["result"]
        with self.assertRaises(PermissionError):
            self.workspace.commit(result["proposal_id"], human_approved=False, authorized=True)
        self.workspace.commit(result["proposal_id"], human_approved=True, authorized=True)
        with self.assertRaises(WorkspaceError):
            self.call("game.console.source.stage", payload)
        with self.assertRaises(WorkspaceError):
            self.workspace.commit(result["proposal_id"], human_approved=True, authorized=True)


if __name__ == "__main__":
    unittest.main()
