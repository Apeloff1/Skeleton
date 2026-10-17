"""Native console animation pixels must originate from exact authored frames.

Tests generate a real original world and actual tiles; assembly is checked as
source, not falsely described as executed native ROM/PPU hardware.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.game_boy_native_export import (
    GameBoySourceError, compile_native_game_boy,
)
from skeleton.ai.game_builder.game_boy_color_native_export import compile_native_game_boy_color
from skeleton.ai.game_builder.nes_native_export import NativeNESError, compile_native_nes
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection, render_studio_art
from skeleton.ai.game_builder.studio_game_boy_rom_art_parity import (
    GameBoyROMArtError, inspect_compiled_game_boy_art,
)
from skeleton.ai.game_builder.studio_nes_chr_parity import (
    NESCHRIntegrityError, inspect_compiled_nes_chr,
)
from skeleton.jeeves.game_console_assets import decode_tiles


class ActualConsoleHeroAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        intent = GameBuildIntent(
            project_id="animated-homebrew", title="Original Animated Hero",
            subtitle="Actual frame-coded handheld and 6502 game source",
            seed=733, width=11, height=11, levels=2,
            collectibles_per_level=2, hazards_per_level=0,
            starting_health=4, theme="forest",
        )
        cls.world = generate_playable_world(intent, authorized=True)
        cls.rights = HomebrewSource(
            project_id="animated-homebrew", platform_id="bandai_wonderswan",
            rights_basis="project_owned",
            evidence_sha256=sha256(b"original-homebrew-frames").hexdigest(),
            creative_identity=("original-hero", "owned-art"),
        )

    def art(self, target, count):
        pack = render_studio_art(
            self.world, target=target, authorized=True,
            direction=ArtDirection(
                style="organic", seed=733, animation_frames=count,
                animation_fps=8, music_density=0, parallax_layers=0,
            ),
        )
        frames = decode_tiles(
            dict(pack.files)["tiles/hero_animation.bin"], pack.codec,
        )
        self.assertEqual(frames[0], pack.runtime_tiles[5])
        self.assertEqual(len(frames), count)
        return pack, frames

    def test_generated_assembly_actually_includes_1_to_4_distinct_native_hero_frames(self):
        implementations = (
            ("nintendo_game_boy", compile_native_game_boy),
            ("nintendo_game_boy_color", compile_native_game_boy_color),
            ("nintendo_famicom", compile_native_nes),
        )
        for target, compile_source in implementations:
            for count in (1, 2, 3, 4):
                with self.subTest(target=target, count=count):
                    pack, frames = self.art(target, count)
                    project = compile_source(
                        self.world, self.rights, authorized=True,
                        tile_art=pack.runtime_tiles, hero_frames=frames,
                        animation_delay=8,
                    )
                    source = project.asm
                    manifest = json.loads(project.manifest_json)
                    self.assertEqual(manifest["native_hero_animation_frames"], count)
                    self.assertEqual(manifest["native_hero_animation_frame_delay"], 8)
                    self.assertEqual(manifest["native_hero_animation_compiled"], count > 1)
                    self.assertNotIn("__ANIMATION_TILES__", source)
                    self.assertNotIn("__ANIM_COUNT__", source)
                    self.assertNotIn("__ANIM_DELAY__", source)
                    self.assertIn("AnimationTiles:", source)
                    self.assertIn("AnimationTilesEnd:", source)
                    self.assertIn("ANIM_COUNT", source)
                    self.assertIn("ANIM_DELAY", source)
                    if count > 1:
                        self.assertIn("hero animation frame 1", source)
                        self.assertIn("AnimFrame", source)
                    self.assertFalse(manifest.get("emulator_verified", False))
                    self.assertFalse(manifest.get("cartridge_built", False))

    def test_invalid_sprite_identity_shape_and_frame_interval_fail(self):
        for target, compile_source, error in (
            ("nintendo_game_boy", compile_native_game_boy, GameBoySourceError),
            ("nintendo_famicom", compile_native_nes, NativeNESError),
        ):
            pack, frames = self.art(target, 3)
            bad_frame = ((1,) * 64,) + frames[1:]
            for changed, delay in (
                (bad_frame, 8), (frames, 0), (frames, 61),
                (frames + frames, 8), (frames[:1] + ((9,) * 64,), 8),
            ):
                with self.subTest(target=target, count=len(changed), delay=delay):
                    with self.assertRaises(error):
                        compile_source(
                            self.world, self.rights, authorized=True,
                            tile_art=pack.runtime_tiles,
                            hero_frames=changed, animation_delay=delay,
                        )

    def test_actual_compiled_handheld_frame_bytes_and_genuine_linker_offsets(self):
        for target in ("nintendo_game_boy", "nintendo_game_boy_color"):
            with TemporaryDirectory() as tmp:
                pack, frames = self.art(target, 4)
                original = dict(pack.files)
                source = Path(tmp)
                (source / "assets/tiles").mkdir(parents=True)
                (source / "assets/tiles/runtime.bin").write_bytes(
                    original["tiles/runtime.bin"]
                )
                (source / "assets/tiles/hero_animation.bin").write_bytes(
                    original["tiles/hero_animation.bin"]
                )
                tile_bytes = original["tiles/runtime.bin"]
                animation_bytes = original["tiles/hero_animation.bin"]
                self.assertEqual(len(tile_bytes), 96)
                self.assertEqual(len(animation_bytes), 64)
                cartridge = bytearray(32768)
                cartridge[0x200:0x260] = tile_bytes
                cartridge[0x260:0x290] = animation_bytes[16:]
                color = target.endswith("_color")
                if color:
                    cartridge[0x143] = 0x80
                check = 0
                for value in cartridge[0x134:0x14D]:
                    check = (check - value - 1) & 255
                cartridge[0x14D] = check
                labels = (
                    b"00:0200 Tiles\n00:0260 TilesEnd\n"
                    b"00:0260 AnimationTiles\n00:0290 AnimationTilesEnd\n"
                )
                evidence = inspect_compiled_game_boy_art(
                    bytes(cartridge), labels, source, color=color,
                )
                self.assertEqual(evidence["original_animation_frame_count"], 4)
                self.assertEqual(evidence["matched_indexed_pixels"], 576)
                self.assertFalse(evidence["emulated_lcd_pixels_verified"])
                cartridge[0x275] ^= 1
                with self.assertRaises(GameBoyROMArtError):
                    inspect_compiled_game_boy_art(
                        bytes(cartridge), labels, source, color=color,
                    )

    def test_compiled_nes_chr_source_animation_integrity_and_mutated_frame(self):
        with TemporaryDirectory() as tmp:
            pack, _ = self.art("nintendo_famicom", 4)
            source = Path(tmp)
            (source / "assets/tiles").mkdir(parents=True)
            items = dict(pack.files)
            first = items["tiles/runtime.bin"]
            frames = items["tiles/hero_animation.bin"]
            (source / "assets/tiles/runtime.bin").write_bytes(first)
            (source / "assets/tiles/hero_animation.bin").write_bytes(frames)
            chr_bank = first + frames[16:]
            cartridge = bytearray(
                b"NES\x1a" + bytes([2, 1]) + bytes(10) + bytes(32768)
                + chr_bank + bytes(8192 - len(chr_bank))
            )
            result = inspect_compiled_nes_chr(bytes(cartridge), source)
            self.assertEqual(result["original_animation_frames_verified"], 4)
            self.assertEqual(result["matched_indexed_pixels"], 576)
            cartridge[16 + 32768 + 99] ^= 1
            with self.assertRaises(NESCHRIntegrityError):
                inspect_compiled_nes_chr(bytes(cartridge), source)


if __name__ == "__main__":
    unittest.main()
