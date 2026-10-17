"""Pixel parity source gate across genuine console tile codecs, HTML5 and Godot."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_campaign import CampaignOrder, run_campaign
from skeleton.ai.game_builder.studio_pixel_parity import (
    StudioPixelParityError, inspect_cross_engine_pixels,
)
from skeleton.ai.game_builder.studio_campaign_assurance import inspect_production_assurance


class OriginalGamePixelParityTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        rights = self.root / "authorship.txt"
        rights.write_text("All original assets and game logic are created here.")
        self.order = CampaignOrder(
            project_id="pixelstudio", title="Multi-Console Pixel Source Parity",
            seed=733, targets=("nintendo_game_boy", "nintendo_famicom",
                               "sega_master_system"),
            source_basis="bandai_wonderswan", rights_document=str(rights),
            creative_identity=("original-sprites", "original-game"),
            width=11, height=11, levels=1, collectibles=1, hazards=1,
            health=4, theme="ocean",
            art=ArtDirection(seed=733, animation_frames=3,
                             parallax_layers=1, music_density=1),
        )
        self.campaign = self.root / "campaign"

    def test_exact_native_browser_and_godot_original_atlas_and_frames(self):
        status = run_campaign(self.order, self.campaign, authorized=True)
        self.assertEqual(status["targets_with_verified_source"], 3)
        for target in self.order.targets:
            with self.subTest(target=target):
                project = self.campaign / "targets" / target
                receipt = inspect_cross_engine_pixels(project)
                self.assertEqual(receipt["matching_semantic_tiles"], 6)
                self.assertEqual(receipt["matching_animation_frames"], 3)
                self.assertEqual(receipt["matching_palette_entries"], 4)
                self.assertEqual(len(receipt["preview_digests"]), 1)
                self.assertFalse(receipt["runtime_graphical_pixels_observed"])
                self.assertFalse(receipt["release_certified"])
                self.assertEqual(receipt["target"], target)
        full = inspect_production_assurance(self.order, self.campaign)
        self.assertEqual(full["checked_gates"], 24)
        self.assertEqual(full["targets_with_exact_source"], 3)
        self.assertEqual(
            full["targets"][0]["gates"]["cross_engine_pixel_art_parity"]["status"],
            "pixel_source_parity_checked",
        )
        self.assertFalse(full["all_targets_release_ready"])

    def test_source_png_tampering_is_not_mistaken_for_parity_success(self):
        run_campaign(self.order, self.campaign, authorized=True, max_targets=1)
        project = self.campaign / "targets/nintendo_game_boy"
        atlas = project / "assets/sprites/atlas.png"
        atlas.write_bytes(atlas.read_bytes() + b"\0")
        with self.assertRaises((StudioPixelParityError, ValueError)):
            inspect_cross_engine_pixels(project)

    def test_executable_browser_tiles_cannot_diverge_from_binary_atlas(self):
        run_campaign(self.order, self.campaign, authorized=True, max_targets=1)
        project = self.campaign / "targets/nintendo_game_boy"
        html = project / "engines/index.html"
        before = html.read_text()
        self.assertIn('"pack_digest"', before)
        changed = before.replace('"pack_digest"', '"old_pack_digest"', 1)
        self.assertNotEqual(before, changed)
        html.write_text(changed)
        with self.assertRaises((StudioPixelParityError, ValueError)):
            inspect_cross_engine_pixels(project)

    def test_wrong_palette_and_invalid_art_receipt_fail_closed(self):
        run_campaign(self.order, self.campaign, authorized=True, max_targets=1)
        project = self.campaign / "targets/nintendo_game_boy"
        descriptor = project / "assets/metadata/descriptors.json"
        info = json.loads(descriptor.read_text())
        info["palette"][0] = "000000ff"
        descriptor.write_text(json.dumps(info))
        with self.assertRaises((StudioPixelParityError, ValueError)):
            inspect_cross_engine_pixels(project)


if __name__ == "__main__":
    unittest.main()
