"""One operator-run studio pass coordinates real stage owners without false E2E."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_campaign import CampaignOrder, run_campaign
from skeleton.ai.game_builder.studio_execution_campaign import (
    ExecutionPolicy, STAGES, StudioExecutionCampaignError,
    run_studio_execution_campaign,
)


class FullStudioExecutionCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        ownership = self.root / "rights.txt"
        ownership.write_text("The original maze, characters and sprites are homebrew")
        self.order = CampaignOrder(
            project_id="campaignrunner", title="Original E2E Production",
            seed=733, targets=("nintendo_game_boy", "nintendo_famicom"),
            source_basis="bandai_wonderswan", rights_document=str(ownership),
            creative_identity=("homebrew-maze", "original-character"),
            width=11, height=11, levels=1, collectibles=1,
            hazards=1, health=4, theme="forest",
            art=ArtDirection(seed=733, music_density=0, parallax_layers=0),
        )
        self.output = self.root / "campaign"

    def test_source_only_real_game_and_stage_progress_has_no_release_claim(self):
        state = run_studio_execution_campaign(
            self.order, self.output, policy=ExecutionPolicy(stages=("source",)),
            authorized=True, execute=True,
        )
        self.assertEqual(state["total_source_targets"], 2)
        self.assertEqual(state["verified_stage_attempts"], 2)
        self.assertEqual(state["total_stage_attempts"], 2)
        self.assertFalse(state["full_release_qualified"])
        self.assertFalse(state["model_weights_updated"])
        self.assertEqual(state["native_roms_verified"], 0)
        self.assertEqual(len(state["run_digest"]), 64)

    def test_real_source_missing_compiler_and_two_optional_emulators_blocked(self):
        with patch(
            "skeleton.ai.game_builder.studio_execution_campaign.qualify_campaign_target",
            return_value={
                "native_rom_compiled": False,
                "blocker": "toolchain_missing:rgbasm",
            },
        ), patch(
            "skeleton.ai.game_builder.studio_execution_campaign.qualify_campaign_emulator",
            return_value={
                "machine_code_victory": False,
                "blocker": "pyboy_not_installed",
            },
        ):
            state = run_studio_execution_campaign(
                self.order, self.output, policy=ExecutionPolicy(
                    stages=("source", "rom", "emulator"),
                ),
                authorized=True, execute=True,
            )
        self.assertEqual(state["verified_stage_attempts"], 2)
        self.assertEqual(state["blocked_stage_attempts"], 4)
        self.assertEqual(state["unsupported_stage_attempts"], 0)
        self.assertEqual(state["native_roms_verified"], 0)
        self.assertEqual(state["compiled_cartridge_victories"], 0)
        self.assertFalse(state["full_release_qualified"])
        self.assertTrue(any(
            event["target"] == "nintendo_famicom"
            and event["stage"] == "emulator"
            and event["status"] == "blocked"
            for event in state["events"]
        ))

    def test_stopping_after_blocker_does_not_mark_remaining_stages_passed(self):
        with patch(
            "skeleton.ai.game_builder.studio_execution_campaign.qualify_campaign_target",
            return_value={"native_rom_compiled": False,
                          "blocker": "toolchain_missing"},
        ):
            state = run_studio_execution_campaign(
                self.order, self.output,
                policy=ExecutionPolicy(
                    stages=("source", "rom", "emulator", "browser"),
                    stop_after_blocker=True,
                ),
                authorized=True, execute=True,
            )
        self.assertTrue(state["interrupted_after_blocker"])
        self.assertEqual([event["stage"] for event in state["events"]],
                         ["source", "source", "rom"])
        self.assertEqual(state["verified_stage_attempts"], 2)
        self.assertFalse(state["full_release_qualified"])

    def test_execute_requires_explicit_operator_authority(self):
        with self.assertRaises(PermissionError):
            run_studio_execution_campaign(
                self.order, self.output,
                policy=ExecutionPolicy(stages=("source",)),
                authorized=False, execute=True,
            )
        with self.assertRaises(StudioExecutionCampaignError):
            run_studio_execution_campaign(
                self.order, self.output,
                policy=ExecutionPolicy(stages=("source",)),
                authorized=True, execute=False,
            )
        self.assertFalse(self.output.exists())

    def test_canvas_capture_never_inherits_general_operator_permission(self):
        with self.assertRaises(StudioExecutionCampaignError):
            ExecutionPolicy(stages=("source", "canvas"), capture_consent=False)
        policy = ExecutionPolicy(
            stages=("source", "canvas"),
            capture_consent=True,
        )
        with patch(
            "skeleton.ai.game_builder.studio_execution_campaign.qualify_campaign_canvas",
            return_value={"generated_game_canvas_recorded": False,
                          "blocker": "playwright_not_available"},
        ) as capture:
            state = run_studio_execution_campaign(
                self.order, self.output,
                policy=policy, authorized=True, execute=True,
            )
        self.assertEqual(capture.call_count, 2)
        self.assertEqual(state["blocked_stage_attempts"], 2)
        self.assertFalse(state["full_release_qualified"])

    def test_unordered_duplicate_or_invalid_stages_fail_before_execution(self):
        for values in (("godot", "source"), ("rom", "rom"), ("training",), ()):
            with self.subTest(values=values):
                with self.assertRaises(StudioExecutionCampaignError):
                    ExecutionPolicy(stages=values)
        self.assertEqual(STAGES[:3], ("source", "rom", "emulator"))
        with self.assertRaises(StudioExecutionCampaignError):
            ExecutionPolicy(max_emulator_frames=0)
        with self.assertRaises(StudioExecutionCampaignError):
            ExecutionPolicy(max_sources_per_run=0)


if __name__ == "__main__":
    unittest.main()
