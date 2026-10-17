"""Resumable studio production: real multi-target sources, tamper rejection and retries."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_campaign import (
    CampaignOrder, StudioCampaignError, inspect_campaign, run_campaign,
)
from skeleton.ai.game_builder.native_game_cli import build_game as real_build_game


class OriginalStudioCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        proof = self.root / "ownership.txt"
        proof.write_text("Original code, characters, game rules and art direction")
        self.order = CampaignOrder(
            project_id="resumablestudio",
            title="Original Multiconsole Dragon Adventure",
            seed=733, targets=("nintendo_game_boy", "nintendo_famicom"),
            source_basis="bandai_wonderswan",
            rights_document=str(proof),
            creative_identity=("original-game", "original-characters"),
            width=11, height=11, levels=1, collectibles=1,
            hazards=1, health=4, theme="space",
            art=ArtDirection(seed=733, animation_frames=2,
                             music_density=1, parallax_layers=1),
        )
        self.output = self.root / "campaign"

    def test_real_multitarget_sources_checkpoints_and_resume(self):
        first = run_campaign(self.order, self.output, authorized=True, max_targets=1)
        self.assertEqual(first["targets_requested"], 2)
        self.assertEqual(first["targets_with_verified_source"], 1)
        self.assertEqual(first["source_completion_percent"], 50)
        self.assertEqual(first["native_roms_compiled"], 0)
        previous = (self.output / "targets/nintendo_game_boy/main.asm").read_bytes()
        next_run = run_campaign(self.order, self.output, authorized=True)
        self.assertEqual(next_run["targets_with_verified_source"], 2)
        self.assertEqual(next_run["source_completion_percent"], 100)
        self.assertEqual(next_run["qualification_percent"], 0)
        self.assertEqual(
            (self.output / "targets/nintendo_game_boy/main.asm").read_bytes(), previous
        )
        for target in self.order.targets:
            root = self.output / "targets" / target
            receipt = json.loads((root / "campaign_receipt.json").read_text())
            self.assertFalse(receipt["native_binary_compiled"])
            self.assertTrue((root / "assets/sprites/atlas.png").is_file())
            self.assertTrue((root / "engines/index.html").is_file())
            self.assertTrue((root / "engines/godot/scripts/main.gd").is_file())
            self.assertIn(target, next_run["completed_targets"])
        self.assertEqual(inspect_campaign(self.order, self.output), next_run)

    def test_rollback_failure_retry_and_unmodified_completed_target(self):
        calls = []

        def failing_once(**kwargs):
            calls.append(kwargs["target"])
            if calls.count("nintendo_game_boy") == 1:
                raise ValueError("simulated native compiler refusal")
            return real_build_game(**kwargs)

        with patch("skeleton.ai.game_builder.studio_campaign.build_game",
                   side_effect=failing_once):
            failed = run_campaign(self.order, self.output, authorized=True)
        self.assertEqual(failed["targets_with_verified_source"], 1)
        self.assertIn("nintendo_game_boy", failed["failures"])
        self.assertFalse((self.output / "targets/nintendo_game_boy").exists())
        other = (self.output / "targets/nintendo_famicom/main.s").read_bytes()
        recovered = run_campaign(self.order, self.output, authorized=True)
        self.assertEqual(recovered["targets_with_verified_source"], 2)
        self.assertFalse(recovered["failures"])
        self.assertEqual((self.output / "targets/nintendo_famicom/main.s").read_bytes(), other)

    def test_tampered_source_or_checkpoint_and_changed_order_fail_closed(self):
        run_campaign(self.order, self.output, authorized=True, max_targets=1)
        old = self.output / "targets/nintendo_game_boy/main.asm"
        old.write_bytes(old.read_bytes() + b"\n; tampered\n")
        with self.assertRaisesRegex(StudioCampaignError, "changed"):
            inspect_campaign(self.order, self.output)
        with self.assertRaises(StudioCampaignError):
            run_campaign(self.order, self.output, authorized=True)
        with self.assertRaises(StudioCampaignError):
            inspect_campaign(replace(self.order, seed=734), self.output)

    def test_concurrent_order_cannot_adopt_or_overwrite_completed_target(self):
        run_campaign(self.order, self.output, authorized=True, max_targets=1)
        with self.assertRaises(StudioCampaignError):
            run_campaign(replace(self.order, targets=self.order.targets[::-1]),
                         self.output, authorized=True)
        with self.assertRaises(PermissionError):
            run_campaign(self.order, self.output, authorized=False)
        with self.assertRaises(StudioCampaignError):
            run_campaign(self.order, self.output, authorized=True, max_targets=0)
        with self.assertRaises(StudioCampaignError):
            CampaignOrder(**{**self.order.__dict__, "targets": ("unsupported",)})
            # dataclass slots intentionally not assumed; this is a negative test


if __name__ == "__main__":
    unittest.main()
