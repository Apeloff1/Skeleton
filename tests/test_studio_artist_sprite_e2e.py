"""Artist-authored actual PNG and Jeeves editable pixel tiles through five consoles."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from dataclasses import replace

from skeleton.jeeves.game_console_assets import png_rgba, decode_png
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.jeeves_app_runtime import dispatch_app_action
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.studio_asset_pipeline import (
    ArtDirection, StudioArtError, _palette, render_studio_art,
)
from skeleton.ai.game_builder.studio_sprite_authoring import (
    StudioSpriteAuthoringError, import_artist_sprite_png,
    palette_identity, typed_artist_tiles,
)
from skeleton.ai.game_builder.native_game_cli import build_game
from skeleton.ai.game_builder.studio_campaign import (
    CampaignOrder, StudioCampaignError, run_campaign,
)


def fixture_tiles():
    return tuple(tuple((index + x + y) % 4
                       for y in range(8) for x in range(8))
                 for index in range(6))


def fixture_png(tiles, colors):
    raw = bytearray(48 * 8 * 4)
    for index, tile in enumerate(tiles):
        for y in range(8):
            for x in range(8):
                offset = (y * 48 + index * 8 + x) * 4
                raw[offset:offset + 4] = bytes(colors[tile[y * 8 + x]])
    return png_rgba(bytes(raw), 48, 8)


def make_intent():
    return GameBuildIntent(
        project_id="originalartproduction", title="Original Hand Drawn Maze",
        subtitle="Editable original human and AI-directed pixel art",
        seed=733, width=11, height=11, levels=1,
        collectibles_per_level=1, hazards_per_level=1,
        starting_health=4, theme="ocean",
    )


class OriginalSpriteAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.colors = _palette("ocean", "classic")
        self.tiles = fixture_tiles()
        self.png = fixture_png(self.tiles, self.colors)
        self.digest = sha256(self.png).hexdigest()
        self.world = generate_playable_world(make_intent(), authorized=True)

    def test_original_png_to_exact_console_tile_bytes_and_engine_pixels(self):
        art = import_artist_sprite_png(
            self.png, expected_sha256=self.digest, palette=self.colors,
            quantization="exact", authorized=True,
        )
        self.assertEqual(art.tiles, self.tiles)
        self.assertEqual(art.palette_digest, palette_identity(self.colors))
        self.assertEqual(art.source_sha256, self.digest)
        for platform in ("nintendo_game_boy", "nintendo_game_boy_color",
                         "nintendo_famicom", "sega_game_gear", "sega_master_system"):
            with self.subTest(platform=platform):
                pack = render_studio_art(
                    self.world, target=platform,
                    direction=ArtDirection(style="etched", seed=733),
                    authorized=True, artist_atlas=art,
                )
                pack.verify()
                self.assertEqual(pack.runtime_tiles, art.tiles)
                self.assertEqual(pack.manifest["artist_source_digest"], self.digest)
                self.assertEqual(pack.manifest["artist_atlas_digest"], art.digest)
                atlas = dict(pack.files)["sprites/atlas.png"]
                self.assertEqual(decode_png(atlas), decode_png(self.png))
                metadata = dict(pack.files)["metadata/descriptors.json"]
                self.assertIn(self.digest.encode(), metadata)

    def test_color_quantization_and_partial_alpha_fail_closed(self):
        modified = bytearray(decode_png(self.png)[2])
        modified[0:3] = b"\x80\x31\x72"
        another = png_rgba(bytes(modified), 48, 8)
        another_hash = sha256(another).hexdigest()
        with self.assertRaises(StudioSpriteAuthoringError):
            import_artist_sprite_png(
                another, expected_sha256=another_hash,
                palette=self.colors, quantization="exact", authorized=True,
            )
        nearest = import_artist_sprite_png(
            another, expected_sha256=another_hash, palette=self.colors,
            quantization="nearest", authorized=True,
        )
        dithered = import_artist_sprite_png(
            another, expected_sha256=another_hash, palette=self.colors,
            quantization="ordered4", authorized=True,
        )
        self.assertEqual(len(nearest.tiles), 6)
        self.assertEqual(len(dithered.tiles), 6)
        self.assertEqual(dithered, import_artist_sprite_png(
            another, expected_sha256=another_hash, palette=self.colors,
            quantization="ordered4", authorized=True,
        ))
        partial = bytearray(decode_png(self.png)[2])
        partial[3] = 128
        data = png_rgba(bytes(partial), 48, 8)
        with self.assertRaises(StudioSpriteAuthoringError):
            import_artist_sprite_png(
                data, expected_sha256=sha256(data).hexdigest(),
                palette=self.colors, quantization="nearest", authorized=True,
            )
        with self.assertRaises(StudioSpriteAuthoringError):
            import_artist_sprite_png(
                self.png, expected_sha256="0" * 64,
                palette=self.colors, quantization="nearest", authorized=True,
            )
        with self.assertRaises(PermissionError):
            import_artist_sprite_png(
                self.png, expected_sha256=self.digest,
                palette=self.colors, quantization="nearest", authorized=False,
            )
        with self.assertRaises(StudioArtError):
            render_studio_art(
                self.world, target="nintendo_game_boy",
                direction=ArtDirection(seed=733, contrast="high"),
                authorized=True,
                artist_atlas=import_artist_sprite_png(
                    self.png, expected_sha256=self.digest,
                    palette=self.colors, quantization="exact", authorized=True,
                ),
            )

    def test_exact_typed_jeeves_art_source_must_still_get_human_approval(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = GameWorkspace.create(root / "work", authorized=True)
            workspace.create_project("originalartproduction", "puzzle", authorized=True)
            pixels = [list(tile) for tile in self.tiles]
            import_art = typed_artist_tiles(pixels, palette=self.colors, authorized=True)
            args = {
                "intent": {
                    "title": self.world.intent.title, "subtitle": self.world.intent.subtitle,
                    "seed": self.world.intent.seed, "width": 11, "height": 11,
                    "levels": 1, "collectibles_per_level": 1,
                    "hazards_per_level": 1, "starting_health": 4, "theme": "ocean",
                },
                "target": "nintendo_game_boy", "source_platform": "bandai_wonderswan",
                "rights_evidence_sha256": sha256(b"original rights").hexdigest(),
                "creative_identity": ["owned-original-art"],
                "style": "etched", "contrast": "classic", "animation_frames": 3,
                "source_file": "main.asm",
                "expected_sha256": sha256(b"").hexdigest(),
                "reason": "Review original pixel-authored homebrew console source",
                "artist_tiles": pixels,
            }
            with self.assertRaises(PermissionError):
                dispatch_app_action(
                    workspace, "originalartproduction",
                    "game.console.source.stage.artwork", args, authorized=False,
                )
            response = dispatch_app_action(
                workspace, "originalartproduction",
                "game.console.source.stage.artwork", args, authorized=True,
            )["result"]
            self.assertTrue(response["actual_native_source_generated"])
            self.assertTrue(response["actual_sprite_pixels_embedded"])
            self.assertEqual(response["artist_sprite_pixel_digest"], import_art.digest)
            self.assertFalse(response["source_committed"])
            with self.assertRaises(PermissionError):
                workspace.commit(response["proposal_id"],
                                 human_approved=False, authorized=True)
            approved = workspace.commit(
                response["proposal_id"], human_approved=True, authorized=True,
            )
            self.assertTrue(approved["approved"])
            self.assertEqual(response["generated_source_sha256"], approved["sha256"])

    def test_multitarget_campaign_binds_artist_png_and_detects_mutation(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            ownership = base / "ownership.txt"
            ownership.write_text("All characters, tiles and gameplay are original")
            image = base / "original.png"
            image.write_bytes(self.png)
            order = CampaignOrder(
                project_id="originalartproduction",
                title="Original Hand Drawn Maze",
                seed=733, targets=("nintendo_game_boy", "nintendo_famicom"),
                source_basis="bandai_wonderswan",
                rights_document=str(ownership),
                creative_identity=("original-art", "original-game"),
                width=11, height=11, levels=1, collectibles=1, hazards=1,
                health=4, theme="ocean", art=ArtDirection(seed=733),
                artist_png=str(image), artist_sha256=self.digest,
                artist_quantization="exact",
            )
            target = base / "campaign"
            status = run_campaign(order, target, authorized=True, max_targets=1)
            self.assertEqual(status["targets_with_verified_source"], 1)
            self.assertTrue((target / "targets/nintendo_game_boy/assets/sprites/atlas.png").is_file())
            image.write_bytes(b"not-a-real-original-image")
            with self.assertRaises(StudioCampaignError):
                run_campaign(order, target, authorized=True)
            self.assertFalse((target / "targets/nintendo_famicom").exists())


if __name__ == "__main__":
    unittest.main()
