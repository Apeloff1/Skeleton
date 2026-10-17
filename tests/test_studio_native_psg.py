"""Original console sound is typed, deterministic and actually emitted as APU code.

Source generation tests do not certify sampled emulator audio or speakers.
"""
from __future__ import annotations

from hashlib import sha256
import json
import unittest

from skeleton.ai.game_builder.game_boy_native_export import (
    GameBoySourceError, compile_native_game_boy,
)
from skeleton.ai.game_builder.game_boy_color_native_export import compile_native_game_boy_color
from skeleton.ai.game_builder.nes_native_export import NativeNESError, compile_native_nes
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.studio_native_psg import (
    NativePSGError, compose_native_psg, console_psg_registers, gb_period, nes_period,
)


class NativeConsolePSGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        world = GameBuildIntent(
            project_id="original-psg", title="Original PSG Studio",
            subtitle="Actual deterministic square wave gameplay audio source",
            seed=733, width=11, height=11, levels=1,
            collectibles_per_level=1, hazards_per_level=0,
            starting_health=4, theme="ocean",
        )
        cls.world = generate_playable_world(world, authorized=True)
        cls.rights = HomebrewSource(
            project_id="original-psg", platform_id="bandai_wonderswan",
            rights_basis="project_owned",
            evidence_sha256=sha256(b"original sound generation").hexdigest(),
            creative_identity=("original-composition", "owned-game-assets"),
        )

    def test_all_themes_and_densities_are_deterministic_unlicensed_pulse_notes(self):
        profiles = []
        for theme in ("forest", "ocean", "desert", "space", "arcade"):
            for density in range(5):
                with self.subTest(theme=theme, density=density):
                    score = compose_native_psg(theme, 733, density)
                    self.assertEqual(score, compose_native_psg(theme, 733, density))
                    self.assertEqual(len(score.note_hz), 8)
                    self.assertEqual(len(score.event_hz), 3)
                    self.assertFalse(score.to_payload()["pcm_soundtrack_bitwise_equal"])
                    self.assertFalse(score.to_payload()["audio_played_on_emulator"])
                    self.assertFalse(score.to_payload()["physical_speaker_verified"])
                    self.assertEqual(len(score.digest), 64)
                    for target in (
                        "nintendo_game_boy", "nintendo_game_boy_color",
                        "nintendo_famicom",
                    ):
                        programmed = console_psg_registers(score, target)
                        self.assertEqual(len(programmed["note_periods"]), 8)
                        self.assertEqual(len(programmed["event_periods"]), 3)
                        self.assertEqual(programmed["enabled"], density > 0)
                        self.assertTrue(all(8 <= v <= 2047 for v in
                                            programmed["note_periods"]))
                        self.assertTrue(all(
                            low + 256 * high == number
                            for low, high, number in zip(
                                programmed["notes_low"], programmed["notes_high"],
                                programmed["note_periods"],
                            )
                        ))
                    profiles.append(score.digest)
        self.assertEqual(len(set(profiles)), len(profiles))

    def test_native_gb_cgb_and_nes_source_contains_real_note_register_writes(self):
        profile = compose_native_psg("ocean", 733, 3)
        for target, compiler, signatures in (
            ("nintendo_game_boy", compile_native_game_boy,
             ("ldh [rNR52], a", "ldh [rNR13], a", "ldh [rNR23], a")),
            ("nintendo_game_boy_color", compile_native_game_boy_color,
             ("ldh [rNR52], a", "ldh [rNR13], a", "ldh [rNR23], a")),
            ("nintendo_famicom", compile_native_nes,
             ("sta $4015", "sta $4002", "sta $4003",
              "sta $4006", "sta $4007")),
        ):
            with self.subTest(target=target):
                compiled = compiler(
                    self.world, self.rights, authorized=True, psg_score=profile,
                )
                asm = compiled.asm
                manifest = json.loads(compiled.manifest_json)
                self.assertTrue(manifest["original_native_psg_integrated"])
                self.assertEqual(manifest["native_psg_score_digest"], profile.digest)
                self.assertFalse(manifest["native_psg_hardware_audio_played"])
                self.assertTrue(manifest["native_psg_not_pcm_identity"])
                self.assertIn("OriginalMusicLow:", asm)
                self.assertIn("OriginalMusicHigh:", asm)
                self.assertIn("SoundPickup:", asm)
                self.assertIn("SoundHazard:", asm)
                self.assertIn("SoundGoal:", asm)
                for expected in signatures:
                    self.assertIn(expected, asm)
                self.assertNotIn("__MUSIC_LOW__", asm)
                self.assertNotIn("__MUSIC_HIGH__", asm)
                self.assertNotIn("__AUDIO_ENABLED__", asm)
                self.assertNotIn("__SFX_PICKUP_LOW__", asm)
                self.assertNotIn("__SFX_GOAL_HIGH__", asm)
                self.assertNotIn("__SFX_HAZARD_LOW__", asm)

    def test_muted_source_suppresses_apu_initialization_at_runtime(self):
        muted = compose_native_psg("ocean", 733, 0)
        for compiler in (compile_native_game_boy, compile_native_nes):
            project = compiler(
                self.world, self.rights, authorized=True, psg_score=muted,
            )
            manifest = json.loads(project.manifest_json)
            self.assertFalse(manifest["original_native_psg_integrated"])
            self.assertIn("AUDIO_ENABLED", project.asm)
            self.assertFalse(manifest["native_psg_hardware_audio_played"])

    def test_hardware_period_bounds_and_wrong_theme_are_rejected(self):
        for value in (0, 89, 1501, 1.5, True):
            with self.subTest(value=value):
                with self.assertRaises(NativePSGError):
                    gb_period(value)
                with self.assertRaises(NativePSGError):
                    nes_period(value)
        for invalid in (-1, 5, 2.5, True):
            with self.assertRaises(NativePSGError):
                compose_native_psg("ocean", 733, invalid)
        wrong = compose_native_psg("space", 733, 3)
        with self.assertRaises(GameBoySourceError):
            compile_native_game_boy(
                self.world, self.rights, authorized=True, psg_score=wrong,
            )
        with self.assertRaises(NativeNESError):
            compile_native_nes(
                self.world, self.rights, authorized=True, psg_score=wrong,
            )


if __name__ == "__main__":
    unittest.main()
