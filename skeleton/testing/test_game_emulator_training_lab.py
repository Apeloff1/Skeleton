"""Synthetic regression harness for training custody (not native compatibility).

No emulator library, commercial ROM, network, or production neural model is
loaded. Behavior/receipt cases must still run against actual native cores before
the corresponding hardware platform can be signed off.
"""
import hashlib
import json
import unittest
from unittest.mock import patch

from skeleton.jeeves.game_emulator_training_lab import (
    EmulatorLabConfig,
    EmulatorTrainingError,
    _collect_audited,
    run_emulator_training_lab,
)
from skeleton.jeeves.game_learning import GameLearningConfig, GamePolicyLearner
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.jeeves.game_learning_runtime import GameEnvironmentSpec, EpisodeStep


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ControlledNativeFixture:
    """Deterministic state machine with a real stateful restore/step interface."""

    def __init__(self, corrupt_replay=False):
        self.spec = GameEnvironmentSpec(
            environment_id="controlled-emulator",
            environment_digest="a" * 64,
            actions=("idle", "left", "right", "a"),
            observation_bins={
                "screen_mean": (0.25, 0.5, 0.75),
                "visual_change": (0.1, 0.5),
                "step_fraction": (0.25, 0.5, 0.75),
            },
            reward_components=("visual_change",),
            max_episode_steps=4,
        )
        self.corrupt_replay = corrupt_replay
        self.replay = False
        self.steps = 0
        self.value = 0
        self.seed = 0
        self.closed = False

    def observation(self):
        return {
            "screen_mean": self.value / 4,
            "visual_change": float(self.value != 0) / 2,
            "step_fraction": self.steps / 4,
        }

    def reset(self, seed=0):
        self.seed = seed
        self.steps = self.value = 0
        return self.observation()

    def step(self, action):
        self.steps += 1
        if action == "left":
            self.value = max(0, self.value - 1)
        if action in ("right", "a"):
            self.value = min(3, self.value + 1)
        observation = self.observation()
        if self.replay and self.corrupt_replay:
            observation["screen_mean"] += 0.125
        return EpisodeStep(
            observation=observation,
            reward_components={"visual_change": observation["visual_change"]},
            terminated=False,
            truncated=self.steps >= self.spec.max_episode_steps,
            info={"evidence": {"frame_digest": _digest(self.value)}},
            transition_digest="",
        )

    def snapshot(self):
        payload = {"steps": self.steps, "value": self.value, "seed": self.seed}
        return {**payload, "state_digest": _digest(payload)}

    def restore(self, snapshot):
        raw = dict(snapshot)
        digest = raw.pop("state_digest")
        if digest != _digest(raw):
            raise ValueError("snapshot corrupted")
        self.steps, self.value, self.seed = raw["steps"], raw["value"], raw["seed"]
        self.replay = True
        return self.observation()

    def preview(self):
        return {"pixels_base64": "AA=="}

    def close(self):
        self.closed = True


def _request():
    return GameEnvironmentRequest(
        target_id="game_boy", kind="builtin", rom_source=b"original fixture",
        max_steps=4,
    )


class EmulatorTrainingCustodyTests(unittest.TestCase):
    def test_requires_rights_acknowledgement(self):
        with self.assertRaises(EmulatorTrainingError):
            run_emulator_training_lab(
                _request(), source_lineage={"rights_acknowledged": False},
                config=EmulatorLabConfig(max_runs=10, steps_per_run=4),
            )

    def test_reverse_replay_and_genuine_q_update(self):
        specimen = ControlledNativeFixture()
        learner = GamePolicyLearner(
            specimen.spec,
            GameLearningConfig(seed=4, max_episodes=10, max_updates=40),
            policy_id="candidate",
            source_lineage={"rights_acknowledged": True, "owner": "synthetic-fixture"},
        )
        with patch.object(GameEnvironmentRequest, "build", return_value=specimen):
            trace, receipt, retained = _collect_audited(
                _request(), learner,
                EmulatorLabConfig(max_runs=10, steps_per_run=4, checkpoint_stride=2),
                run_index=0, seed=2, angle="exploration",
                cancel=None, authorize=None,
            )
        self.assertEqual(trace["steps"], 4)
        self.assertTrue(receipt["reverse_checkpoints"])
        self.assertGreaterEqual(receipt["actual_replay_steps"], 4)
        self.assertEqual(receipt["model_neural_weights_updated"], 0)
        self.assertEqual(retained["trace_digest"], trace["trace_digest"])
        trained = learner.train_offline([trace])
        self.assertEqual(trained.updates, 4)
        self.assertEqual(learner.snapshot()["committed_updates"], 4)

    def test_divergent_restored_native_state_refuses_training_receipt(self):
        specimen = ControlledNativeFixture(corrupt_replay=True)
        learner = GamePolicyLearner(
            specimen.spec, GameLearningConfig(max_episodes=10, max_updates=40),
            policy_id="tamper-probe",
            source_lineage={"rights_acknowledged": True},
        )
        with patch.object(GameEnvironmentRequest, "build", return_value=specimen):
            with self.assertRaises(EmulatorTrainingError):
                _collect_audited(
                    _request(), learner, EmulatorLabConfig(max_runs=10, steps_per_run=4),
                    run_index=0, seed=0, angle="boundary",
                    cancel=None, authorize=None,
                )
        self.assertEqual(learner.snapshot()["committed_updates"], 0)

    def test_full_session_keeps_neural_promotion_false(self):
        config = EmulatorLabConfig(
            max_runs=11, steps_per_run=4, stagnation_runs=10,
            checkpoint_stride=2, boomerang_interval=2, boomerang_retained=2,
            heldout_episodes=1,
        )
        with patch.object(GameEnvironmentRequest, "build", side_effect=ControlledNativeFixture):
            report = run_emulator_training_lab(
                _request(), source_lineage={"rights_acknowledged": True, "operator": "fixture"},
                config=config,
            )
        self.assertGreaterEqual(report["run_count"], 1)
        self.assertEqual(report["actual_training_steps"], 4 * report["run_count"])
        self.assertEqual(report["actual_q_table_updates"], report["actual_training_steps"])
        self.assertEqual(report["actual_neural_parameter_updates"], 0)
        self.assertTrue(report["limits"]["visual_novelty_is_not_game_success"])
        self.assertTrue(report["boomerang_replay_receipts"])
        self.assertNotEqual(report["report_digest"], "")


if __name__ == "__main__":
    unittest.main()
