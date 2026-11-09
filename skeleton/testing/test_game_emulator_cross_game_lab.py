"""Run *real original source CPU ROMs* through the 2..30 game comparer.

Only generated single-cartridge ROMs, no copyright material or provider AI,
no installed libretro binary, no promoted model weights. Native core execution
must be separately run in an approved operator environment.
"""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from scripts.audit_original_gameboy_cpu_opcodes import _cartridge
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.jeeves.game_emulator_cross_game_lab import (
    CrossGameConfig, CrossGameComparisonError, _validate,
    compare_real_emulator_games, verify_cross_game_comparison_receipt,
    _digest,
)
from skeleton.jeeves.game_rom_runtime import GameBoyROMEnvironment


def original_loop(title: int) -> bytes:
    rom = bytearray(_cartridge(0x00))
    rom[0x100:0x103] = bytes((0xC3, 0x00, 0x01))  # Actual JP $0100 CPU instruction.
    rom[0x105] = title & 255
    return bytes(rom)


def approved_request(variation: int) -> GameEnvironmentRequest:
    return GameEnvironmentRequest(
        target_id="game_boy", kind="builtin",
        rom_source=original_loop(variation),
        max_steps=8, cycles_per_step=512,
    )


PROGRAMS = (
    ("idle",),
    ("a",),
    ("right", "idle", "a"),
    ("a_right", "idle", "right"),
)


class ControlledSourceMultiGameExperiments(unittest.TestCase):
    def test_two_real_original_roms_same_actions_independent_source_replays(self):
        result = compare_real_emulator_games(
            [approved_request(1), approved_request(2)],
            PROGRAMS, rights_acknowledged=True,
        )
        self.assertEqual(result["selected_games"], 2)
        self.assertEqual(result["actual_replayed_game_programs"], 16)
        self.assertEqual(result["actual_source_action_steps"], 32)
        self.assertEqual(result["completed_sequential_waves"], 1)
        self.assertEqual(result["actual_native_executions_concurrent"], 1)
        self.assertEqual(len(result["pairwise_measured_evidence"]), 1)
        self.assertFalse(result["pairwise_measured_evidence"][0]["gameplay_skill_or_causation_established"])
        self.assertEqual(result["ai_training_gradient_updates"], 0)
        self.assertEqual(result["candidate_numeric_source_rows"], 16)
        self.assertEqual(len(result["candidate_numeric_dataset_sha256"]), 64)
        self.assertFalse(result["cross_game_feature_alignment_inferred"])
        for game in result["game_receipts"]:
            self.assertEqual(len(game["controller_programs"]), 4)
            self.assertEqual(game["source_kind"], "builtin")
            for phase in game["controller_programs"]:
                self.assertTrue(phase["exact_source_replay_verified"])
                self.assertEqual(len(phase["controlled_source_step_receipts"]),
                                 len(phase["controller_program"]))
                for transition in phase["controlled_source_step_receipts"]:
                    self.assertEqual(len(transition["measured_source_projection_sha256"]), 64)
                    self.assertIsNone(transition["declared_native_transition_sha256"])
                    self.assertIsInstance(transition["source_observation"], dict)
                    self.assertIsInstance(transition["source_next_observation"], dict)
                    self.assertIsInstance(transition["source_reward_components"], dict)
                    self.assertIsInstance(transition["source_visual_change_observed"], bool)

    def test_rehashed_fake_frame_and_pairwise_metrics_cannot_pass_source_gate(self):
        real = compare_real_emulator_games(
            [approved_request(1), approved_request(2)],
            PROGRAMS, rights_acknowledged=True,
        )
        self.assertTrue(verify_cross_game_comparison_receipt(real)["accepted"])
        cases = (
            ("reported_frame_change", lambda item:
                item["game_receipts"][0]["controller_programs"][0].__setitem__(
                    "actual_frame_change_events", 1
                )),
            ("changed_action_order", lambda item:
                item["game_receipts"][0]["controller_programs"][2][
                    "controlled_source_step_receipts"][0].__setitem__("action", "b")),
            ("invented_pairwise_difference", lambda item:
                item["pairwise_measured_evidence"][0].__setitem__(
                    "visual_event_rate_differences", [1.0] * len(PROGRAMS)
                )),
            ("invented_neural_learning", lambda item:
                item.__setitem__("ai_training_gradient_updates", 99)),
            ("fabricated_numeric_reward", lambda item:
                item["game_receipts"][0]["controller_programs"][0][
                    "controlled_source_step_receipts"][0]["source_reward_components"].__setitem__(
                        "visual_change", 0.875
                    )),
            ("tampered_numeric_dataset_digest", lambda item:
                item.__setitem__("candidate_numeric_dataset_sha256", "f" * 64)),
        )
        for label, change in cases:
            with self.subTest(label=label):
                forged = copy.deepcopy(real)
                change(forged)
                forged["report_digest"] = _digest({
                    k: v for k, v in forged.items() if k != "report_digest"
                })
                with self.assertRaises(CrossGameComparisonError):
                    verify_cross_game_comparison_receipt(forged)

    def test_three_owned_ROM_variants_keep_source_identities_and_waves_separate(self):
        report = compare_real_emulator_games(
            [approved_request(1), approved_request(2), approved_request(3)],
            (("idle",), ("a",), ("right",)),
            rights_acknowledged=True, config=CrossGameConfig(games_per_wave=2),
        )
        self.assertEqual(report["completed_sequential_waves"], 2)
        self.assertEqual([row["wave"] for row in report["game_receipts"]], [0, 0, 1])
        self.assertEqual(len(report["pairwise_measured_evidence"]), 3)
        self.assertEqual(len({r["request_digest"] for r in report["game_receipts"]}), 3)
        self.assertFalse(report["cross_game_rewards_equivalent"])

    def test_reject_inert_or_unsupported_controller_programs_before_build(self):
        requests = [approved_request(1), approved_request(2)]
        bad = (
            (("a",), ("idle",)),  # No passive control first.
            (("idle",), ("a",), ("a",)),  # Duplicate program.
            (("idle",), ("jump",)),  # Unknown game action alias.
            (("idle",), ("a",) * 9),  # Unbounded program.
        )
        for programs in bad:
            with self.subTest(programs=programs):
                with self.assertRaises(CrossGameComparisonError):
                    compare_real_emulator_games(
                        requests, programs, rights_acknowledged=True,
                    )

    def test_duplicate_ROM_and_unapproved_source_kinds_cannot_inflate_ai_results(self):
        p = approved_request(1)
        with self.assertRaises(CrossGameComparisonError):
            compare_real_emulator_games([p, p], PROGRAMS, rights_acknowledged=True)
        with self.assertRaises(CrossGameComparisonError):
            compare_real_emulator_games([approved_request(1), approved_request(2)],
                                        PROGRAMS, rights_acknowledged=False)

    def test_exact_source_replay_divergence_fails_without_any_weight_promotion(self):
        from skeleton.jeeves.game_emulator_cross_game_lab import _run_program
        real = _run_program
        calls = {"number": 0}

        def corrupt_second_pass(environment, snapshot, program):
            result = real(environment, snapshot, program)
            calls["number"] += 1
            if calls["number"] == 2:
                result = dict(result)
                result["source_end_snapshot_sha256"] = "f" * 64
            return result

        with patch(
            "skeleton.jeeves.game_emulator_cross_game_lab._run_program",
            side_effect=corrupt_second_pass,
        ):
            with self.assertRaisesRegex(CrossGameComparisonError, "replay"):
                compare_real_emulator_games(
                    [approved_request(1), approved_request(2)],
                    PROGRAMS, rights_acknowledged=True,
                )

    def test_truncation_and_step_budgets_are_checked_before_game_execution(self):
        over = tuple((("idle",),) * 7)
        with self.assertRaises(CrossGameComparisonError):
            compare_real_emulator_games(
                [approved_request(1), approved_request(2)],
                over, rights_acknowledged=True,
            )
        reqs = [
            GameEnvironmentRequest(
                target_id="game_boy", kind="builtin", rom_source=original_loop(n),
                max_steps=2, cycles_per_step=512,
            )
            for n in (1, 2)
        ]
        with self.assertRaises(CrossGameComparisonError):
            compare_real_emulator_games(reqs, PROGRAMS, rights_acknowledged=True)


if __name__ == "__main__":
    unittest.main()
