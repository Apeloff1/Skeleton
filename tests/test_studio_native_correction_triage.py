"""Dragon forms narrow source-bound corrections; neither trains nor edits AI."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.studio_campaign import CampaignOrder
from skeleton.ai.game_builder.studio_native_correction_triage import (
    triage_native_gameplay,
)


def _history(current=True, fields=None, category="cpu_state_diverged"):
    return {
        "campaign_identity": "a" * 64,
        "current_assurance_report_digest": "b" * 64,
        "history_digest": "c" * 64,
        "latest_run_digest": "d" * 64,
        "latest_still_matches_current_source": current,
        "recorded_cpu_divergence_events": 1,
        "latest_cpu_divergence": {
            "target": "nintendo_famicom",
            "category": category, "diagnostic_digest": "e" * 64,
            "first_action": 17, "changed_fields": fields or [],
        },
    }


class DragonNativeCorrectionTests(unittest.TestCase):
    def setUp(self):
        from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
        self.order = CampaignOrder(
            project_id="read-only-failure", title="Read-Only Repair",
            seed=733, targets=("nintendo_famicom",),
            source_basis="bandai_wonderswan",
            rights_document="/unused/original-rights",
            creative_identity=("homebrew-art", "game-builder"),
            width=11, height=11, levels=1, collectibles=1,
            hazards=0, health=4, theme="forest",
            art=ArtDirection(seed=733, music_density=0, parallax_layers=0),
        )

    def project(self, history):
        with patch(
            "skeleton.ai.game_builder.studio_native_correction_triage.inspect_execution_history",
            return_value=history,
        ):
            return triage_native_gameplay(
                self.order, Path("/source/current"), authorized=True,
            )

    def test_repeated_score_bytes_map_to_one_actionable_corrective_plan(self):
        result = self.project(_history(fields=[
            "PlayerX", "Score", "ScoreHigh", "TurnCount",
        ]))
        self.assertEqual(result["proposal_count"], 3)
        self.assertEqual(
            [x["category"] for x in result["proposals"]],
            [
                "directional_input_or_collision",
                "collectible_goal_score_divergence",
                "missed_or_repeated_controller_turn",
            ],
        )
        self.assertEqual(result["proposals"][0]["first_mismatch_action"], 17)
        self.assertFalse(result["model_weights_modified"])
        self.assertFalse(result["knowledge_promoted"])
        self.assertFalse(result["source_code_modified"])
        self.assertTrue(all(
            not row["automatic_code_edit_allowed"] and row["must_retest_original_game"]
            for row in result["proposals"]
        ))
        self.assertEqual(len(result["triage_digest"]), 64)

    def test_stale_history_never_becomes_current_repair_advice(self):
        result = self.project(_history(current=False, fields=["Health"]))
        self.assertTrue(result["stale_history_proposals_blocked"])
        self.assertEqual(result["proposal_count"], 0)
        self.assertEqual(result["proposals"], [])

    def test_qualified_source_failure_triage_distinguishes_art_from_cpu_and_staleness(self):
        original = _history(fields=["Score"])
        original["latest_stage_blockers"] = [
            {
                "target": "nintendo_game_boy", "stage": "rom",
                "category": "compiled_sprite_mismatch",
                "recommended_review": "Compare exact original tile bytes and RGBLINK labels",
            },
            {
                "target": "nintendo_game_boy", "stage": "emulator",
                "category": "gameboy_emulator_unavailable",
                "recommended_review": "Provision approved PyBoy and retry exact original ROM",
            },
            {
                "target": "nintendo_game_boy", "stage": "emulator",
                "category": "controller_or_gameplay_divergence",
                "recommended_review": "Inspect original CPU trace",
            },
        ]
        result = self.project(original)
        self.assertEqual(
            [row["category"] for row in result["proposals"]],
            ["collectible_goal_score_divergence", "compiled_sprite_mismatch",
             "gameboy_emulator_unavailable"],
        )
        self.assertTrue(all(not row["automatic_code_edit_allowed"]
                            for row in result["proposals"]))
        original["latest_still_matches_current_source"] = False
        stale = self.project(original)
        self.assertEqual(stale["proposal_count"], 0)
        self.assertTrue(stale["stale_history_proposals_blocked"])

    def test_missing_cpu_log_requires_new_real_execution(self):
        result = self.project(_history(category="sample_count_mismatch"))
        self.assertEqual(result["proposal_count"], 1)
        self.assertEqual(
            result["proposals"][0]["category"],
            "incomplete_or_invalid_emulator_telemetry",
        )
        with self.assertRaises(PermissionError):
            triage_native_gameplay(self.order, "/unused", authorized=False)


if __name__ == "__main__":
    unittest.main()
