"""Actual HTML5 audio and parallax output uses generated ORIGINAL WAV/PNG bytes.

Browser resource playback is opt-in through a user movement: these tests
validate source/data integration, not audible device output or GPU quality.
"""
from __future__ import annotations

from hashlib import sha256
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_campaign import CampaignOrder, run_campaign
from skeleton.ai.game_builder.studio_pixel_parity import _game_json


class StudioPlayableAudioAndEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        ownership = self.root / "rights.txt"
        ownership.write_text("Original music, assets and game source")
        self.order = CampaignOrder(
            project_id="musicaudiogame", title="Original Sound Stage",
            seed=733, targets=("nintendo_game_boy",),
            source_basis="bandai_wonderswan",
            rights_document=str(ownership),
            creative_identity=("original-music", "original-tiles"),
            width=11, height=11, levels=1, collectibles=1, hazards=1,
            health=4, theme="ocean",
            art=ArtDirection(seed=733, music_density=3, parallax_layers=2,
                             animation_frames=3),
        )
        self.folder = self.root / "campaign"
        state = run_campaign(self.order, self.folder, authorized=True)
        self.assertEqual(state["targets_with_verified_source"], 1)
        self.game = self.folder / "targets/nintendo_game_boy"

    def test_same_pcm_and_parallax_png_bytes_are_in_actual_html5_runtime(self):
        html = (self.game / "engines/index.html").read_text()
        game = _game_json(html)
        media = game["studio_media"]
        self.assertEqual(set(media["audio"]), {"ambient", "collectible", "hazard"})
        for kind in media["audio"]:
            actual = (self.game / f"assets/audio/{kind}.wav").read_bytes()
            embedded = base64.b64decode(media["audio"][kind], validate=True)
            self.assertEqual(sha256(actual).digest(), sha256(embedded).digest())
            self.assertTrue(embedded.startswith(b"RIFF"))
        self.assertEqual(len(media["parallax"]), 2)
        for i, payload in enumerate(media["parallax"]):
            self.assertEqual(
                base64.b64decode(payload, validate=True),
                (self.game / f"assets/parallax/layer_{i:02d}.png").read_bytes(),
            )
        self.assertIn('media-src data:', html)
        self.assertIn('img-src data:', html)
        self.assertIn('music-volume', html)
        self.assertIn('effects-volume', html)
        self.assertIn('music-mute', html)
        self.assertIn('playStudioCue("collectible")', html)
        self.assertIn('playStudioCue("hazard")', html)
        self.assertIn('ctx.drawImage(picture', html)
        self.assertIn('musicMuted=!musicMuted', html)

    def test_without_pcm_disabled_audio_has_no_phantom_ambient_stream(self):
        art = ArtDirection(
            seed=733, music_density=0, parallax_layers=1, animation_frames=3,
        )
        from skeleton.ai.game_builder.playable_world import (
            GameBuildIntent, generate_playable_world,
        )
        from skeleton.ai.game_builder.studio_asset_pipeline import render_studio_art
        from skeleton.ai.game_builder.playable_export import render_playable_world
        intent = GameBuildIntent(
            project_id="musicaudiogame", title="Mute Project",
            subtitle="No synthesized WAV tracks", seed=733, width=11,
            height=11, levels=1, collectibles_per_level=1,
            hazards_per_level=1, starting_health=4, theme="ocean",
        )
        world = generate_playable_world(intent, authorized=True)
        original_art = render_studio_art(
            world, target="nintendo_game_boy", direction=art, authorized=True,
        )
        html = render_playable_world(
            world, studio_art=original_art, authorized=True,
        )
        contents = _game_json(html.html)
        self.assertEqual(contents["studio_media"]["audio"], {})
        self.assertEqual(len(contents["studio_media"]["parallax"]), 1)
        self.assertIn('!STUDIO_MEDIA.audio.ambient', html.html)


if __name__ == "__main__":
    unittest.main()
