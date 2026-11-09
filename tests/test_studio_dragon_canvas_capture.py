"""Consent-only graphical capture of original game (never user desktop)."""
from __future__ import annotations

from pathlib import Path
import json
from skeleton.ai.game_builder.studio_campaign_assurance import (
    inspect_production_assurance, qualify_campaign_canvas,
)
from skeleton.ai.game_builder.studio_e2e_observation import observe_production_campaign
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_campaign import CampaignOrder, run_campaign
from skeleton.ai.game_builder.studio_dragon_canvas_capture import (
    DragonCanvasCaptureError, _png_geometry, capture_generated_game,
)


class DragonGeneratedCanvasCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        rights = self.root / "authorship.txt"
        rights.write_text("Source, original characters, images and music are original")
        order = CampaignOrder(
            project_id="dragoncanvas", title="Original Observed Game",
            seed=733, targets=("nintendo_game_boy",),
            source_basis="bandai_wonderswan", rights_document=str(rights),
            creative_identity=("original-characters", "original-pixel-art"),
            width=11, height=11, levels=1, collectibles=1,
            hazards=1, health=4, theme="ocean",
            art=ArtDirection(seed=733, music_density=0, parallax_layers=0),
        )
        self.order = order
        self.campaign = self.root / "campaign"
        state = run_campaign(order, self.campaign, authorized=True)
        self.assertEqual(state["targets_with_verified_source"], 1)
        self.engine = self.campaign / "targets/nintendo_game_boy/engines"
        self.destination = self.root / "private-game-frames"

    def test_requires_two_distinct_consent_and_execute_boundaries(self):
        for authorized, consent, execute in ((False, True, True),
                                              (True, False, True)):
            with self.subTest(authorized=authorized, consent=consent):
                with self.assertRaises(PermissionError):
                    capture_generated_game(
                        self.engine, self.destination, authorized=authorized,
                        capture_consent=consent, execute=execute,
                    )
        with self.assertRaises(DragonCanvasCaptureError):
            capture_generated_game(
                self.engine, self.destination, authorized=True,
                capture_consent=True, execute=False,
            )
        with self.assertRaises(DragonCanvasCaptureError):
            capture_generated_game(
                self.engine, self.destination, authorized=True,
                capture_consent=True, execute=True, timeout_seconds=0,
            )
        self.assertFalse(self.destination.exists())

    def test_missing_browser_is_not_reported_as_visual_recording(self):
        with patch("skeleton.ai.game_builder.studio_dragon_canvas_capture.importlib.util.find_spec",
                   return_value=None):
            report = capture_generated_game(
                self.engine, self.destination,
                authorized=True, capture_consent=True, execute=True,
            )
        self.assertFalse(report["framebuffer_recorded"])
        self.assertEqual(report["blocker"], "playwright_not_available")
        self.assertFalse(report["model_training_authorized"])
        self.assertFalse(report["user_screen_recorded"])
        self.assertFalse(self.destination.exists())

    def test_png_dimensions_and_unapproved_paths_are_fail_closed(self):
        with self.assertRaises(DragonCanvasCaptureError):
            _png_geometry(b"not-a-graphic")
        self.destination.mkdir()
        with self.assertRaises(DragonCanvasCaptureError):
            capture_generated_game(
                self.engine, self.destination, authorized=True,
                capture_consent=True, execute=True,
            )

    def test_real_browser_canvas_recording_when_runtime_installed(self):
        from importlib.util import find_spec
        if find_spec("playwright") is None:
            self.skipTest("opt-in graphical browser instrumentation is not installed")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
                browser.close()
            except Exception:
                self.skipTest("Chromium runtime not installed; no fabricated visual proof")
        output = qualify_campaign_canvas(
            self.order, self.campaign, "nintendo_game_boy",
            authorized=True, capture_consent=True, execute=True,
            timeout_seconds=60,
        )
        self.assertTrue(output["generated_game_canvas_recorded"])
        self.assertFalse(output["model_training_authorized"])
        frames = (self.campaign / "qualifications/nintendo_game_boy/canvas_capture")
        saved = json.loads((frames / "capture.json").read_text())
        self.assertTrue(saved["graphical_browser_pixels_observed"])
        self.assertFalse(saved["user_screen_recorded"])
        self.assertFalse(saved["model_training_authorized"])
        replay = json.loads((self.engine / "proof/verified_solution.json").read_text())
        self.assertEqual(saved["world_digest"], replay["world_digest"])
        self.assertGreaterEqual(len(saved["frames"]), 2)
        self.assertLessEqual(len(saved["frames"]), 3)
        self.assertTrue((frames / "frame_00.png").is_file())
        report = inspect_production_assurance(self.order, self.campaign)
        self.assertEqual(report["generated_game_canvas_captures_verified"], 1)
        self.assertEqual(
            report["targets"][0]["gates"]["generated_game_canvas_frames_recorded"]["status"],
            "generated_game_canvas_pixels_recorded",
        )
        observation = observe_production_campaign(
            self.order, self.campaign, authorized=True,
        )
        self.assertEqual(observation["generated_game_canvas_captures"], 1)
        self.assertFalse(observation["learned_new_weights"])
        again = qualify_campaign_canvas(
            self.order, self.campaign, "nintendo_game_boy",
            authorized=True, capture_consent=True, execute=True,
        )
        self.assertTrue(again["already_qualified"])


if __name__ == "__main__":
    unittest.main()
