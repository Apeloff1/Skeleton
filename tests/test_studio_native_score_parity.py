"""Native scoring source contract against the actual Python winning replay.

These tests inspect emitted assembly templates and execute the Python
reference. They do not imply the assembler/emulator actually ran.
"""
from __future__ import annotations

import unittest

from skeleton.ai.game_builder.game_boy_native_export import _ASM as GB_ASM
from skeleton.ai.game_builder.nes_native_export import _ASM as NES_ASM
from skeleton.ai.game_builder.playable_world import (
    GameBuildIntent, generate_playable_world,
)
from skeleton.ai.game_builder.playable_simulation import demonstrate_solvable


class OriginalGameNativeScoreParityTests(unittest.TestCase):
    def test_generated_native_templates_have_full_16_bit_score_arithmetic(self):
        self.assertIn("ScoreHigh: ds 1", GB_ASM)
        self.assertIn("TurnCount: ds 1", GB_ASM)
        self.assertIn("TurnCountHigh: ds 1", GB_ASM)
        self.assertIn("    ld [TurnCount], a", GB_ASM)
        self.assertIn("ld [ScoreHigh], a", GB_ASM)
        self.assertIn("    add 10", GB_ASM)
        self.assertIn("    add 100", GB_ASM)
        self.assertIn("    ld [Level], a\n    cp LEVEL_COUNT", GB_ASM)
        self.assertIn("ScoreHigh: .res 1", NES_ASM)
        self.assertIn("TurnCount: .res 1", NES_ASM)
        self.assertIn("TurnCountHigh: .res 1", NES_ASM)
        self.assertIn("    inc TurnCount", NES_ASM)
        self.assertIn("    inc TurnCountHigh", NES_ASM)
        self.assertIn(".exportzp Level, PlayerX, PlayerY, Health, Score, ScoreHigh", NES_ASM)
        self.assertIn("    adc #10", NES_ASM)
        self.assertIn("    adc #100", NES_ASM)
        self.assertIn("    inc ScoreHigh", NES_ASM)
        self.assertIn("    sta ScoreHigh", NES_ASM)

    def test_real_python_game_scores_goal_and_collectibles_across_levels(self):
        intent = GameBuildIntent(
            project_id="original-score-parity", title="Long score",
            subtitle="Native source must match full reference total",
            seed=733, width=11, height=11, levels=3,
            collectibles_per_level=2, hazards_per_level=1,
            starting_health=4, theme="forest",
        )
        world = generate_playable_world(intent, authorized=True)
        replay = demonstrate_solvable(world, authorized=True)
        self.assertEqual(replay.final_state.status, "won")
        self.assertEqual(replay.final_state.score, 3 * (2 * 10 + 100))
        self.assertGreater(replay.final_state.score, 255)
        self.assertEqual(
            (replay.final_state.score & 255) + 256 * (replay.final_state.score >> 8),
            replay.final_state.score,
        )


if __name__ == "__main__":
    unittest.main()
