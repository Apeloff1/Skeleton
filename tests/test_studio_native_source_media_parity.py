"""Native studio requires exact original sprite/audio assembly before ROM build.

Uses actual generated original worlds and browser/Godot/asset packages, not an
invented JSON report. No compiler, emulator, soundcard or release is claimed.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.native_game_cli import build_game
from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_native_source_media_parity import (
    NativeMediaSourceError, inspect_native_source_media,
)


class TrueOriginalConsoleMediaSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rights = self.root / "original-author-evidence.txt"
        self.rights.write_text(
            "Original homebrew story, cast, game, tiles, music, animation and mechanics",
            encoding="utf-8",
        )

    def generate(self, target, *, frames=3, density=3):
        folder = self.root / target
        receipt = build_game(
            target=target, basis="bandai_wonderswan",
            project_id="native-media-proof", title="Original Sound and Motion",
            seed=733, width=11, height=11, levels=2,
            collectibles=2, hazards=0, health=4,
            rights_evidence=self.rights,
            creative_identity=("original-characters", "independently-authored-sound"),
            output=folder, authorized=True,
            studio_art=ArtDirection(
                seed=733, style="organic", animation_frames=frames,
                animation_fps=8, music_density=density, parallax_layers=0,
            ),
        )
        self.assertFalse(receipt["native_binary_built"])
        return folder, receipt

    def test_all_three_native_consoles_match_actual_source_music_and_animation(self):
        for platform in (
            "nintendo_game_boy", "nintendo_game_boy_color", "nintendo_famicom",
        ):
            with self.subTest(platform=platform):
                folder, built = self.generate(platform)
                receipt = inspect_native_source_media(folder, target=platform)
                self.assertTrue(receipt["console_assembly_data_verified"])
                self.assertEqual(receipt["original_hero_frame_count"], 3)
                self.assertEqual(receipt["native_animation_ticks_per_frame"], 8)
                self.assertEqual(receipt["native_psg_score_digest"],
                                 built["native_psg_score_digest"])
                self.assertEqual(receipt["native_gameplay_cues"], 3)
                self.assertEqual(receipt["native_music_notes"], 8)
                self.assertTrue(receipt["native_psg_enabled"])
                self.assertFalse(receipt["native_machine_code_executed"])
                self.assertFalse(receipt["console_video_verified"])
                self.assertFalse(receipt["audio_hardware_verified"])
                self.assertEqual(len(receipt["source_media_digest"]), 64)

    def test_static_frame_and_muted_original_sound_remain_explicit(self):
        folder, built = self.generate(
            "nintendo_game_boy", frames=1, density=0,
        )
        receipt = inspect_native_source_media(
            folder, target="nintendo_game_boy",
        )
        self.assertEqual(receipt["original_hero_frame_count"], 1)
        self.assertFalse(receipt["native_psg_enabled"])
        self.assertFalse(built["native_psg_music_and_cues_source_integrated"])

    def test_silent_source_mutations_fail_before_rom_compilation(self):
        folder, _ = self.generate("nintendo_game_boy")
        original = folder / "main.asm"
        unmodified = original.read_text(encoding="utf-8")
        swaps = (
            ("DEF ANIM_COUNT EQU 3", "DEF ANIM_COUNT EQU 2"),
            ("DEF MUSIC_FRAME_DELAY EQU 17", "DEF MUSIC_FRAME_DELAY EQU 18"),
            ("AnimationTiles:\n", "AnimationTiles:\n    db $00, $00\n"),
            ("OriginalMusicLow:\n", "OriginalMusicLow:\n    db $00\n"),
            ("SoundPickup:\n", "SoundPickup:\n    ret\n"),
            ("    call TickOriginalMusic\n",
             "    ; intentionally bypass native original audio\n"),
            ("    call AnimateHero\n",
             "    ; intentionally bypass native sprite animation\n"),
            ("    call InitOriginalAudio\n",
             "    ; intentionally skip console APU setup\n"),
        )
        for before, after in swaps:
            with self.subTest(before=before):
                self.assertIn(before, unmodified)
                original.write_text(
                    unmodified.replace(before, after, 1), encoding="utf-8",
                )
                with self.assertRaises(NativeMediaSourceError):
                    inspect_native_source_media(
                        folder, target="nintendo_game_boy",
                    )
        original.write_text(unmodified, encoding="utf-8")
        self.assertTrue(inspect_native_source_media(
            folder, target="nintendo_game_boy",
        )["console_assembly_data_verified"])

    def test_sound_table_mutation_rejected_in_actual_nes_assembly(self):
        folder, _ = self.generate("nintendo_famicom")
        program = folder / "main.s"
        original = program.read_text(encoding="utf-8")
        self.assertIn("OriginalMusicHigh:\n", original)
        self.assertIn("    jsr TickOriginalMusic\n", original)
        program.write_text(
            original.replace(
                "OriginalMusicHigh:\n",
                "OriginalMusicHigh:\n.byte $00, $01, $02\n", 1,
            ), encoding="utf-8",
        )
        with self.assertRaises(NativeMediaSourceError):
            inspect_native_source_media(folder, target="nintendo_famicom")

    def test_non_console_platforms_and_wrong_target_are_not_qualified(self):
        folder, _ = self.generate("nintendo_game_boy")
        for other in ("nintendo_famicom", "nintendo_switch", "", None):
            with self.subTest(other=other):
                with self.assertRaises(NativeMediaSourceError):
                    inspect_native_source_media(folder, target=other)


if __name__ == "__main__":
    unittest.main()
