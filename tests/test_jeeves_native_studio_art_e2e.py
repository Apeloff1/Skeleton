"""Real console asset generation, source inclusion, previews and failure paths.

These are offline source/build tests, not emulator or hardware qualification.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import wave
from unittest.mock import patch
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.game_boy_native_export import (
    GameBoySourceError, compile_native_game_boy, _tile_bytes,
)
from skeleton.ai.game_builder.game_boy_color_native_export import compile_native_game_boy_color
from skeleton.ai.game_builder.nes_native_export import (
    NativeNESError, compile_native_nes, _nes_chr,
)
from skeleton.ai.game_builder.sega_8bit_native_export import (
    compile_native_sega_8bit, _tiles as _sega_tiles,
)
from skeleton.ai.game_builder.sms_native_export import compile_native_sms
from skeleton.ai.game_builder.native_game_cli import build_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.studio_asset_pipeline import (
    ArtDirection, StudioArtError, export_studio_art, render_studio_art,
)
from skeleton.jeeves.game_console_assets import decode_png, decode_tiles
from skeleton.ai.game_builder.contracts import canonical_digest


def make_world():
    intent = GameBuildIntent(
        project_id="jeeves-native-art-e2e", title="Original Dragon Art Studio",
        subtitle="A playable game with real authored pixels.",
        seed=733, width=11, height=11, levels=2,
        collectibles_per_level=1, hazards_per_level=1,
        theme="ocean", starting_health=4,
    )
    return generate_playable_world(intent, authorized=True)


def make_rights():
    return HomebrewSource(
        project_id="jeeves-native-art-e2e", platform_id="bandai_wonderswan",
        rights_basis="project_owned", evidence_sha256=sha256(b"human owned").hexdigest(),
        creative_identity=("original-characters", "original-rule-set"),
    )


class StudioProductionAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = make_world()
        cls.rights = make_rights()

    def test_real_pixels_descriptors_palette_animation_and_preview(self):
        art = ArtDirection(style="organic", contrast="high", animation_frames=4, seed=19)
        pack = render_studio_art(self.world, target="nintendo_famicom",
                                 direction=art, authorized=True)
        pack.verify()
        files = dict(pack.files)
        self.assertEqual(len(pack.runtime_tiles), 6)
        self.assertEqual(pack.manifest["animation_frames_rendered"], 4)
        self.assertEqual(len(decode_tiles(files["tiles/runtime.bin"], pack.codec)), 6)
        self.assertEqual(len(decode_tiles(files["tiles/hero_animation.bin"], pack.codec)), 4)
        self.assertNotEqual(files["sprites/hero_frame_00.png"],
                            files["sprites/hero_frame_01.png"])
        self.assertNotEqual(files["sprites/hero_frame_00.png"],
                            files["sprites/hero_frame_02.png"])
        descriptors = json.loads(files["metadata/descriptors.json"])
        self.assertEqual(descriptors["sprites"][5]["id"], "hero")
        self.assertEqual(descriptors["animation"]["fps"], 4)
        self.assertTrue(descriptors["runtime_art_source_embedded"])
        self.assertFalse(descriptors["animation"]["native_animation_driver_integrated"])
        self.assertEqual(len(descriptors["sprites"]), 6)
        for level in self.world.levels:
            width, height, pixels = decode_png(files[f"previews/level_{level.index:02d}.png"])
            self.assertEqual((width, height),
                             (self.world.intent.width * 8, self.world.intent.height * 8))
            self.assertEqual(len(pixels), width * height * 4)
        width, height, pixels = decode_png(files["sprites/atlas.png"])
        self.assertEqual((width, height), (48, 8))
        self.assertEqual(len(pixels), width * height * 4)

    def test_deterministic_build_variants_and_mutation_detected(self):
        direction = ArtDirection(style="arcade", seed=391, animation_frames=3)
        a = render_studio_art(self.world, target="nintendo_game_boy",
                              direction=direction, authorized=True)
        b = render_studio_art(self.world, target="nintendo_game_boy",
                              direction=direction, authorized=True)
        self.assertEqual(a, b)
        other = render_studio_art(self.world, target="nintendo_game_boy",
                                  direction=replace(direction, style="etched"), authorized=True)
        self.assertNotEqual(a.digest, other.digest)
        broken = dict(a.files)
        broken["tiles/runtime.bin"] = b"NO"
        with self.assertRaises(StudioArtError):
            replace(a, files=tuple(sorted(broken.items()))).verify()

    def test_generated_tiles_are_in_real_cartridge_source(self):
        for target in ("nintendo_game_boy", "nintendo_game_boy_color", "nintendo_famicom",
                       "sega_game_gear", "sega_master_system"):
            with self.subTest(target=target):
                art = render_studio_art(
                    self.world, target=target,
                    direction=ArtDirection(style="luminous", seed=1897),
                    authorized=True,
                )
                if target == "sega_game_gear":
                    built = compile_native_sega_8bit(
                        self.world, self.rights, target, authorized=True, tile_art=art.runtime_tiles)
                    legacy = compile_native_sega_8bit(
                        self.world, self.rights, target, authorized=True)
                    self.assertIn(_sega_tiles(art.runtime_tiles), built.game_c)
                    self.assertNotEqual(legacy.game_c, built.game_c)
                elif target == "sega_master_system":
                    built = compile_native_sms(
                        self.world, self.rights, authorized=True, tile_art=art.runtime_tiles)
                    legacy = compile_native_sms(self.world, self.rights, authorized=True)
                    self.assertNotEqual(legacy.asm, built.asm)
                elif target == "nintendo_famicom":
                    built = compile_native_nes(
                        self.world, self.rights, authorized=True, tile_art=art.runtime_tiles
                    )
                    legacy = compile_native_nes(self.world, self.rights, authorized=True)
                    self.assertIn(_nes_chr(art.runtime_tiles), built.asm)
                    self.assertNotEqual(legacy.asm, built.asm)
                elif target == "nintendo_game_boy_color":
                    built = compile_native_game_boy_color(
                        self.world, self.rights, authorized=True, tile_art=art.runtime_tiles
                    )
                    legacy = compile_native_game_boy_color(self.world, self.rights,
                                                           authorized=True)
                    self.assertIn(_tile_bytes(art.runtime_tiles), built.asm)
                    self.assertNotEqual(legacy.asm, built.asm)
                else:
                    built = compile_native_game_boy(
                        self.world, self.rights, authorized=True, tile_art=art.runtime_tiles
                    )
                    legacy = compile_native_game_boy(self.world, self.rights, authorized=True)
                    self.assertIn(_tile_bytes(art.runtime_tiles), built.asm)
                    self.assertNotEqual(legacy.asm, built.asm)
                record = json.loads(built.manifest_json)
                self.assertTrue(record["custom_original_tile_pixels_in_native_source"])
                self.assertEqual(
                    record["generated_runtime_art_tile_digest"],
                    canonical_digest([list(tile) for tile in art.runtime_tiles]),
                )
                self.assertNotEqual(legacy.content_digest, built.content_digest)
                compile_flags = ("binary_compiled", "rom_compiled", "cartridge_built",
                                 "native_cartridge_compiled")
                self.assertTrue(any(
                    getattr(built, name) is False
                    for name in compile_flags if hasattr(built, name)
                ))

    def test_real_pcm_audio_parallax_foliage_and_shadow_controls(self):
        direction = ArtDirection(
            style="organic", music_density=4, parallax_layers=3,
            shadow_strength=3, foliage_density=4, animation_fps=12, seed=1501,
        )
        pack = render_studio_art(self.world, target="nintendo_game_boy",
                                 direction=direction, authorized=True)
        pack.verify()
        files = dict(pack.files)
        self.assertEqual(pack.manifest["environment_overlay_layers_rendered"], 3)
        self.assertEqual(pack.manifest["original_pcm_cues_generated"], 3)
        self.assertFalse(pack.manifest["native_audio_driver_integrated"])
        self.assertFalse(pack.manifest["native_parallax_driver_integrated"])
        desc = json.loads(files["metadata/descriptors.json"])
        self.assertEqual(desc["animation"]["fps"], 12)
        self.assertEqual(desc["shadow_strength"], 3)
        self.assertEqual(desc["foliage_density"], 4)
        for layer in range(3):
            width, height, pixels = decode_png(files[f"parallax/layer_{layer:02d}.png"])
            self.assertEqual((width, height), (11 * 8, 11 * 8))
            self.assertTrue(any(pixels[offset + 3] > 0 for offset in range(0, len(pixels), 4)))
        for kind, seconds in (("ambient", 4), ("collectible", 1), ("hazard", 1)):
            payload = files[f"audio/{kind}.wav"]
            with wave.open(BytesIO(payload), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), 8000)
                self.assertEqual(wav.getnframes(), 8000 * seconds)
        second = render_studio_art(self.world, target="nintendo_game_boy",
                                   direction=direction, authorized=True)
        self.assertEqual(pack, second)
        without = render_studio_art(
            self.world, target="nintendo_game_boy",
            direction=replace(direction, foliage_density=0, shadow_strength=0,
                              music_density=0, parallax_layers=0), authorized=True)
        self.assertNotEqual(without.runtime_tiles, pack.runtime_tiles)
        self.assertFalse(any(name.startswith("audio/") for name, _ in without.files))
        self.assertFalse(any(name.startswith("parallax/") for name, _ in without.files))
        for kwargs in (
            {"foliage_density": True}, {"shadow_strength": 4},
            {"music_density": 5}, {"parallax_layers": -1}, {"animation_fps": 0},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(StudioArtError):
                ArtDirection(**kwargs)

    def test_native_cartridge_rejects_corrupt_art_and_unauthorized_creation(self):
        with self.assertRaises(PermissionError):
            render_studio_art(self.world, target="nintendo_famicom",
                              direction=ArtDirection(), authorized=False)
        with self.assertRaises(StudioArtError):
            render_studio_art(self.world, target="not-a-console",
                              direction=ArtDirection(), authorized=True)
        with self.assertRaises(GameBoySourceError):
            compile_native_game_boy(self.world, self.rights, authorized=True,
                                    tile_art=((0,) * 64,))
        with self.assertRaises(NativeNESError):
            compile_native_nes(self.world, self.rights, authorized=True,
                               tile_art=((0,) * 64,))
        with self.assertRaises(StudioArtError):
            ArtDirection(animation_frames=999)
        with self.assertRaises(StudioArtError):
            ArtDirection(seed=True)

    def test_full_native_cli_outputs_sources_and_real_asset_files(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = root / "authorship.txt"
            evidence.write_text("Original characters and homebrew project design")
            for target in ("nintendo_game_boy", "nintendo_famicom",
                           "sega_master_system", "sega_game_gear", "dos_vga"):
                folder = root / target
                result = build_game(
                    target=target, basis="bandai_wonderswan",
                    project_id="jeeves-native-art-e2e", title="Original Dragon Art Studio",
                    seed=733, width=11, height=11, levels=2,
                    collectibles=1, hazards=1, health=4,
                    rights_evidence=evidence,
                    creative_identity=("original-characters", "original-rule-set"),
                    output=folder, authorized=True,
                    studio_art=ArtDirection(seed=107, style="etched", animation_frames=3),
                )
                self.assertTrue(folder.is_dir())
                self.assertTrue((folder / "assets/tiles/runtime.bin").is_file())
                self.assertTrue((folder / "assets/previews/level_00.png").is_file())
                self.assertTrue((folder / "assets/sprites/hero_frame_02.png").is_file())
                self.assertTrue((folder / "assets/audio/ambient.wav").is_file())
                self.assertTrue((folder / "assets/audio/collectible.wav").is_file())
                self.assertTrue((folder / "assets/audio/hazard.wav").is_file())
                self.assertTrue((folder / "assets/parallax/layer_00.png").is_file())
                manifest = json.loads((folder / "assets/metadata/manifest.json").read_text())
                self.assertEqual(manifest["pack_digest"], result["studio_assets"]["pack_digest"])
                self.assertFalse(result["native_binary_built"])
                self.assertFalse(result["emulator_verified"])
                engines = result["engine_sources"]
                self.assertIsNotNone(engines)
                self.assertTrue(engines["browser_source_rendered"])
                self.assertTrue(engines["godot4_source_rendered"])
                self.assertTrue(engines["interactive_tile_editor_source"])
                self.assertTrue(engines["actual_winning_python_replay"])
                self.assertEqual(engines["world_digest"], result["world_digest"])
                self.assertFalse(engines["godot_binary_executed"])
                self.assertTrue(engines["runtime_uses_custom_asset_tiles"])
                self.assertTrue(engines["actual_browser_sprite_rasterizer_embedded"])
                self.assertTrue(engines["godot_source_sprite_rasterizer_embedded"])
                self.assertFalse(engines["godot_sprite_renderer_executed"])
                script = (folder / "engines/index.html").read_text()
                self.assertIn("function drawStudioTile", script)
                self.assertIn("STUDIO_ART.frames[spriteFrame]", script)
                self.assertIn("window.setInterval", script)
                self.assertIn("STUDIO_ART = GAME.studio_art", script)
                self.assertIn(manifest["pack_digest"], script)
                gdscript = (folder / "engines/godot/scripts/main.gd").read_text()
                self.assertIn("func _draw_studio_tile", gdscript)
                self.assertIn("func _load_studio_art", gdscript)
                self.assertIn("func _process(delta: float)", gdscript)
                self.assertIn("sprite_frame_index", gdscript)
                engine_art = json.loads((
                    folder / "engines/godot/studio_art.json").read_text())
                self.assertEqual(engine_art["pack_digest"], manifest["pack_digest"])
                self.assertEqual(len(engine_art["tiles"]), 6)
                self.assertEqual(len(engine_art["palette"]), 4)
                self.assertEqual(len(engine_art["frames"]), 3)
                self.assertEqual(engine_art["fps"], 4)
                self.assertIn("<html", (folder / "engines/index.html").read_text().lower())
                self.assertIn("extends Control", (
                    folder / "engines/godot/scripts/main.gd").read_text())
                self.assertTrue((folder / "engines/proof/verified_solution.json").is_file())
                if target in {"nintendo_game_boy", "nintendo_famicom",
                              "sega_master_system", "sega_game_gear"}:
                    self.assertTrue(result["native_art_embedded"])
                else:
                    self.assertFalse(result["native_art_embedded"])
                with self.assertRaises(FileExistsError):
                    build_game(
                        target=target, basis="bandai_wonderswan",
                        project_id="jeeves-native-art-e2e", title="Original Dragon Art Studio",
                        seed=733, width=11, height=11, levels=2,
                        collectibles=1, hazards=1, health=4,
                        rights_evidence=evidence,
                        creative_identity=("original-characters", "original-rule-set"),
                        output=folder, authorized=True,
                        studio_art=ArtDirection(seed=107),
                    )

    def test_native_export_failure_leaves_no_partial_source_or_media_directory(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = root / "authorship.txt"
            evidence.write_text("Only original homebrew materials")
            destination = root / "new-build"
            kwargs = {
                "target": "nintendo_game_boy",
                "basis": "bandai_wonderswan",
                "project_id": "jeeves-native-art-e2e",
                "title": "Original Dragon Art Studio",
                "seed": 733, "width": 11, "height": 11, "levels": 1,
                "collectibles": 1, "hazards": 1, "health": 4,
                "rights_evidence": evidence,
                "creative_identity": ("original-characters", "independent-mechanics"),
                "output": destination, "authorized": True,
                "studio_art": ArtDirection(seed=299),
            }
            with patch(
                "skeleton.ai.game_builder.native_game_cli.export_studio_art",
                side_effect=StudioArtError("simulated late asset-stage fault"),
            ):
                with self.assertRaisesRegex(StudioArtError, "late asset-stage"):
                    build_game(**kwargs)
            self.assertFalse(destination.exists())
            self.assertFalse(any(
                path.name.startswith(".jeeves-native-studio-")
                for path in root.iterdir()
            ))
            result = build_game(**kwargs)
            self.assertTrue(destination.is_dir())
            self.assertEqual(result["output_directory"], str(destination))
            self.assertEqual(result["studio_assets"]["assets_directory"],
                             str(destination / "assets"))
            self.assertEqual(result["engine_sources"]["path"],
                             str(destination / "engines"))

    def test_bundle_export_denies_replay_and_never_overwrites(self):
        pack = render_studio_art(self.world, target="nintendo_game_boy",
                                 direction=ArtDirection(), authorized=True)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(PermissionError):
                export_studio_art(pack, root, authorized=False)
            result = export_studio_art(pack, root, authorized=True)
            self.assertEqual(result["pack_digest"], pack.digest)
            source = root / "assets/tiles/runtime.bin"
            before = source.read_bytes()
            with self.assertRaises(FileExistsError):
                export_studio_art(pack, root, authorized=True)
            self.assertEqual(source.read_bytes(), before)
            self.assertTrue(decode_png((root / "assets/previews/level_00.png").read_bytes()))


if __name__ == "__main__":
    unittest.main()
