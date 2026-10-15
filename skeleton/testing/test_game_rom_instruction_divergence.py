"""Real original-ROM CPU replay and controlled-input microtrace regressions.

No native libretro, commercial ROM, provider LLM or game-IP downloads. Uses
actual source GameBoyMachine CPU instructions and deterministic save/restore.
"""

from __future__ import annotations

import copy
import unittest

from skeleton.jeeves.game_rom_instruction_divergence import (
    InstructionDivergenceConfig, InstructionDivergenceError,
    _first_difference, compare_original_rom_instruction_branches,
)


class InstructionSourceReplayCases(unittest.TestCase):
    def test_actual_generated_cpu_instruction_trace_is_repeated_from_exact_state(self):
        report = compare_original_rom_instruction_branches(
            InstructionDivergenceConfig(
                seed=7,
                instruction_count=256,
                sample_stride=4,
                max_cycles_per_branch=8192,
                action_subset=("idle", "a", "right"),
            ),
        )
        self.assertTrue(report["all_source_replays_identical"])
        self.assertEqual(report["real_source_instruction_executions"], 1536)
        self.assertEqual(len(report["paired_replay_verified_differences"]), 2)
        for case in report["actual_passive_and_controller_interventions"]:
            self.assertEqual(case["actual_repeated_physical_cpu_runs"], 2)
            self.assertEqual(case["first_run"]["real_source_cpu_instructions"], 256)
            self.assertEqual(case["first_run"]["source_state_before_inputs_sha256"],
                             report["exact_boot_source_checkpoint_sha256"])
            self.assertEqual(case["first_run"]["real_source_sample_count"], 65)
            self.assertTrue(case["source_replay_identical"])
        self.assertFalse(report["production_jeeves_model_promotion"])
        self.assertEqual(report["neural_or_q_training_updates"], 0)

    def test_source_microtrace_separates_register_timer_and_full_ram_differences(self):
        baseline = {
            "time_and_video_evidence": [
                {"after_instruction_ordinal": 0,
                 "sample_digest": "a" * 64,
                 "real_cpu_registers": {"pc": 1},
                 "real_div_timer_interrupts": {"tima": 1},
                 "real_mapper_control": {"rom_bank": 1},
                 "native_source_memory_sha256": {"wram_full_sha256": "a" * 64},
                 "authored_goal_memory": {"score": 0},
                 "actual_cpu_schedule_cycles": 4,
                 "actual_frame_count": 0},
            ],
        }
        active = copy.deepcopy(baseline)
        active["time_and_video_evidence"][0]["real_div_timer_interrupts"]["tima"] = 2
        active["time_and_video_evidence"][0]["sample_digest"] = "b" * 64
        result = _first_difference(baseline, active)
        self.assertTrue(result["actual_source_control_difference_observed"])
        self.assertEqual(result["first_sample_ordinal"], 0)
        self.assertIn("real_div_timer_interrupts", result["changed_measured_domains"])
        self.assertFalse(result["game_objective_success_proven"])

    def test_sample_budget_fails_before_any_source_cpu_execution(self):
        for invalid in [
            {"instruction_count": 16384, "sample_stride": 1},
            {"instruction_count": 2048, "sample_stride": 1},
            {"instruction_count": 4096, "sample_stride": 16, "max_cycles_per_branch": 512},
            {"action_subset": ("a", "idle")},
            {"action_subset": ("idle", "idle")},
            {"action_subset": ("idle", "hyperdrive")},
        ]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(InstructionDivergenceError):
                    InstructionDivergenceConfig(**invalid)


if __name__ == "__main__":
    unittest.main()
