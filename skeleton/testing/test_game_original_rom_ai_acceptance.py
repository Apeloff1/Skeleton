"""Original-ROM full-pipeline acceptance regressions.

The positive case runs the REAL original Game Boy instruction interpreter,
actual savestate replays, Q-learning and a bounded CPU neural optimizer.
It requires no downloaded ROM, commercial IP, libretro core, network access
or external service. These tests are authored here, not claimed executed.
"""

from __future__ import annotations

import unittest

from scripts.accept_original_rom_ai_pipeline import (
    OriginalAcceptanceError,
    run_original_rom_ai_pipeline,
)
from skeleton.jeeves.game_emulator_neural_world import (
    verify_neural_training_sources, validate_neural_world_checkpoint,
)


class OriginalRomAcceptanceTests(unittest.TestCase):
    def test_generate_execute_rewind_fit_neural_and_check_holdout(self):
        raw, policy, evidence, model, measured, result = run_original_rom_ai_pipeline(
            seed=11,
            max_runs=10,
            episode_steps=4,
            neural_epochs=1,
            neural_width=4,
        )
        self.assertGreater(len(raw), 0)
        self.assertEqual(result["actual_replay_audited_q_runs"], evidence["run_count"])
        self.assertEqual(
            result["actual_learning_state_action_steps"],
            evidence["actual_q_table_updates"],
        )
        self.assertEqual(result["actual_q_updates"], evidence["actual_training_steps"])
        self.assertEqual(result["verified_neural_source_rows"], result["actual_q_updates"])
        self.assertTrue(result["actual_candidate_neural_optimizer_steps"] > 0)
        self.assertEqual(
            validate_neural_world_checkpoint(model), result["candidate_neural_model_sha256"]
        )
        sample, fields, actions, digest = verify_neural_training_sources(evidence, policy)
        self.assertEqual(len(sample), result["verified_neural_source_rows"])
        self.assertEqual(digest, result["source_q_report_digest"])
        self.assertTrue(fields and actions)
        self.assertFalse(result["native_libretro_core_executed"])
        self.assertFalse(result["physical_hardware_execution"])
        self.assertFalse(result["production_model_promotion_authorized"])
        self.assertFalse(result["production_jeeves_weights_changed"])
        self.assertEqual(
            result["acceptance_gate_passed"],
            measured["candidate_status"] == "candidate_predictive_gain_measured",
        )

    def test_unbounded_seed_training_and_optimizer_budget_refused(self):
        cases = [
            {"seed": -1},
            {"max_runs": 256},
            {"episode_steps": 1000},
            {"neural_epochs": 9999},
            {"neural_width": 512},
        ]
        for config in cases:
            with self.subTest(config=config):
                with self.assertRaises(OriginalAcceptanceError):
                    run_original_rom_ai_pipeline(**config)


if __name__ == "__main__":
    unittest.main()
