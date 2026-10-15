"""Strict synthetic regressions for operator-authored native RAM goal experiments.

No commercial content, BIOS, installed libretro core or actual native machine
is used in this test source. Real ROM execution must be demonstrated separately.
"""
import unittest
from unittest.mock import patch

from skeleton.jeeves.game_emulator_goal_lab import (
    MemoryGoal, GoalExperimentConfig, EmulatorGoalError, evaluate_operator_native_goals,
)
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.testing.test_game_emulator_advanced_experiments import ControlledGame


def request():
    return GameEnvironmentRequest(
        target_id="emulator:game_boy", kind="libretro",
        core_id="gambatte", registry_digest="a" * 64,
        rom_source=b"original synthesized cartridge", max_steps=12,
    )


class OperatorNativeGoalCases(unittest.TestCase):
    def test_exact_source_goal_interventions_have_fair_neutral_controls(self):
        config = GoalExperimentConfig(
            seed=8, anchors=2, repeats=3, horizon=3, max_actual_steps=128,
        )
        goal = MemoryGoal(
            "declared-score-register", region=0, offset=0,
            bytes_per_value=2, direction="increase", threshold=1,
        )
        with patch.object(GameEnvironmentRequest, "build",
                          side_effect=lambda **_: ControlledGame()):
            receipt = evaluate_operator_native_goals(
                request(), goals=[goal],
                interventions={
                    "single_input_and_recovery": ["a"],
                    "held_input": ["a", "a", "a"],
                    "reverse_input": ["left", "left", "left"],
                },
                rights_acknowledged=True,
                source_authority="Operator claims original ROM and memory register role",
                config=config,
            )
        self.assertEqual(receipt["actual_source_steps"], 55)
        self.assertEqual(len(receipt["source_anchors"]), 2)
        self.assertGreaterEqual(receipt["measured_active_only_goal_contrasts"], 2)
        self.assertFalse(receipt["semantics"]["game_meanings_independently_certified"])
        self.assertFalse(receipt["semantics"]["policy_or_model_promotion"])
        for anchor in receipt["source_anchors"]:
            for experiment in anchor["interventions"]:
                self.assertEqual(len(experiment["executed_horizon_actions"]), 3)
                self.assertEqual(
                    len(experiment["source_active_repetitions"]), config.repeats,
                )
                self.assertTrue(
                    all(trial["completed_horizon"]
                        for trial in experiment["source_active_repetitions"])
                )
                for trial in experiment["source_active_repetitions"]:
                    self.assertEqual(
                        trial["source_memory_witnesses"][0]["source_start"][
                            "declared_address"
                        ]["region"], 0,
                    )

    def test_operator_memory_goal_range_validation(self):
        with self.assertRaises(EmulatorGoalError):
            MemoryGoal("invalid core region", region=7, offset=0)
        with self.assertRaises(EmulatorGoalError):
            MemoryGoal("empty bitmask", region=0, offset=0, direction="bit_set")
        with self.assertRaises(EmulatorGoalError):
            MemoryGoal("signed bitmask", region=0, offset=0,
                       direction="bit_clear", signed=True, mask=2)
        with self.assertRaises(EmulatorGoalError):
            MemoryGoal("illegal width", region=0, offset=0, bytes_per_value=8)

    def test_no_approved_native_core_no_goal_certification(self):
        built = GameEnvironmentRequest(
            target_id="game_boy", kind="builtin",
            rom_source=b"original synthesized cartridge", max_steps=12,
        )
        with self.assertRaises(EmulatorGoalError):
            evaluate_operator_native_goals(
                built, goals=[MemoryGoal("score", 0, 0)],
                interventions={"press": ["a"]},
                rights_acknowledged=True, source_authority="operator owned",
            )

    def test_rejects_underbudget_and_unacknowledged_source(self):
        with self.assertRaises(EmulatorGoalError):
            evaluate_operator_native_goals(
                request(), goals=[MemoryGoal("score", 0, 0)],
                interventions={"press": ["a"]},
                rights_acknowledged=False, source_authority="owned",
            )
        with self.assertRaises(EmulatorGoalError):
            evaluate_operator_native_goals(
                request(), goals=[MemoryGoal("score", 0, 0)],
                interventions={"press": ["a"] * 3},
                rights_acknowledged=True, source_authority="owned",
                config=GoalExperimentConfig(
                    anchors=4, repeats=4, horizon=16,
                    max_actual_steps=8,
                ),
            )


if __name__ == "__main__":
    unittest.main()
