"""Synthetic physical-planning and temporal-audio rewind regression contracts.

Fixtures exercise real Python state mutation, restore, checksum validation and
the candidate planner orchestration. They do not certify a native emulator,
commercial game, hardware renderer or production model optimization.
"""

import base64
import copy
import hashlib
import json
import threading
import unittest
from unittest.mock import patch

from skeleton.jeeves.game_emulator_host import (
    _EMPTY, _measured_signal_channels,
    _temporal_signal_channels,
    EmulatorEnvironment, EmulatorHostError,
)
from skeleton.jeeves.game_emulator_neural_world import (
    SCHEMA as MODEL_SCHEMA, _init_parameters,
)
from skeleton.jeeves.game_emulator_planning_lab import (
    EmulatorPlanningConfig, EmulatorPlanningError, run_native_confirmed_planning,
)
from skeleton.jeeves.game_learning_runtime import GameEnvironmentSpec
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest

from skeleton.testing.test_game_emulator_advanced_experiments import ControlledGame


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def fake_host():
    host = object.__new__(EmulatorEnvironment)
    host._lock = threading.RLock()
    host._closed = False
    host._process = None
    host._temporary = None
    host._prepared_owner = None
    host._seed = 3
    host._steps = 2
    host.max_steps = 8
    host._chain = "e" * 64
    host._audio_total = 4
    host._audio_generation = 1
    host._controls = [copy.deepcopy(_EMPTY)]
    host._pixels = bytes([20, 40, 60] * 4)
    host._audio = bytes([1, 0, 2, 0] * 4)
    host._frame = {
        "width": 2, "height": 2, "format": "rgb24",
        "pixel_sha256": hashlib.sha256(host._pixels).hexdigest(),
        "rotation": 0, "video_callbacks": 1, "runs": 2,
        "audio_frames": 4, "sample_rate": 44100.0, "fps": 60.0,
        "audio_available": True, "shutdown": False,
    }
    values = [1, 2] * 4
    spectral = _measured_signal_channels(host._pixels, 2, 2, values)
    temporal = _temporal_signal_channels(None, host._pixels, 2, 2, b"", host._audio)
    features = {
        "screen_mean": sum(host._pixels) / (255 * len(host._pixels)),
        "visual_change": 0.25,
        "audio_rms": 0.02,
        "step_fraction": 0.25,
        **spectral, **temporal,
    }
    host.spec = GameEnvironmentSpec(
        environment_id="fake-native", environment_digest="a" * 64,
        actions=("idle", "a"), observation_bins={
            name: (0.25, 0.5, 0.75) for name in features
        },
        reward_components=("visual_change",), max_episode_steps=8,
    )
    host._observation = features
    commands = []

    def exchange(command, payload, blocks=None):
        commands.append(command)
        if command == "state_info":
            return {"state_size": 4}, {}
        if command == "snapshot":
            blob = b"ABCD"
            return {"state_size": 4, "state_sha256": hashlib.sha256(blob).hexdigest()}, {"state": blob}
        if command == "restore":
            assert blocks is not None and blocks["state"] == b"ABCD"
            return {}, {}
        raise AssertionError("unexpected native command " + command)

    host._exchange = exchange
    return host, commands


def neural_candidate(spec):
    features, actions = list(spec.observation_bins), list(spec.actions)
    width = 4
    model = {
        "schema_version": MODEL_SCHEMA,
        "network": "two_hidden_layer_tanh_dense_reward_and_observation_delta",
        "source_evidence_digest": "b" * 64,
        "source_policy_snapshot_digest": "c" * 64,
        "source_environment_digest": spec.environment_digest,
        "observation_features": features,
        "actions": actions,
        "input_dimensions": len(features) + len(actions),
        "hidden_width": width,
        "output_dimensions": len(features) + 1,
        "normalization_means_train_only": [0.0] * len(features),
        "normalization_std_train_only": [1.0] * len(features),
        "reward_scale_train_only": 1.0,
        "parameters": _init_parameters(len(features) + len(actions), width, len(features) + 1, seed=42),
        "parameter_count": 0,
        "real_optimizer_steps": 1,
        "gradient_evaluations": 3,
        "actual_neural_parameter_training_executed": True,
        "production_model_promotion_authorized": False,
        "not_a_jeeves_transformer_update": True,
        "heldout_results_not_used_for_optimization": True,
        "measured_predictive_gate": "candidate_predictive_gain_measured",
    }
    model["parameter_count"] = sum(len(part) for part in model["parameters"].values())
    model["model_digest"] = digest(model)
    report = {
        "schema_version": "skeleton.game.emulator_neural_training_report.v1",
        "world_model_digest": model["model_digest"],
        "candidate_status": "candidate_predictive_gain_measured",
    }
    report["report_digest"] = digest(report)
    return model, report


def native_request():
    return GameEnvironmentRequest(
        target_id="game_boy", max_steps=8, kind="builtin",
        rom_source=b"original owned synthetic test data",
    )


class AudioSavestateRegression(unittest.TestCase):
    def test_rewind_preserves_previous_audio_for_next_measured_step(self):
        host, commands = fake_host()
        try:
            snapshot = host.snapshot()
            self.assertEqual(snapshot["audio_size"], 16)
            self.assertEqual(
                base64.b64decode(snapshot["audio_base64"]), bytes([1, 0, 2, 0] * 4),
            )
            host._audio = bytes([4, 0, 5, 0] * 4)
            host._pixels = bytes([0] * 12)
            host._steps = 6
            returned = host.restore(snapshot)
            self.assertEqual(host._audio, bytes([1, 0, 2, 0] * 4))
            self.assertEqual(host._steps, 2)
            self.assertEqual(returned, snapshot["observation"])
            self.assertEqual(snapshot["snapshot_digest"], host.snapshot()["snapshot_digest"])
            self.assertIn("restore", commands)
        finally:
            host.close()

    def test_inner_audio_checksum_rejects_recomputed_outer_snapshot(self):
        host, _ = fake_host()
        try:
            state = host.snapshot()
            state["audio_base64"] = base64.b64encode(bytes([6, 0, 7, 0] * 4)).decode()
            payload = {key: value for key, value in state.items() if key != "snapshot_digest"}
            state["snapshot_digest"] = digest(payload)
            with self.assertRaises(EmulatorHostError):
                host.restore(state)
        finally:
            host.close()


class MeasuredNeuralPlanningRegression(unittest.TestCase):
    def test_physical_rollout_neutral_comparison_does_not_train_or_promote(self):
        model, report = neural_candidate(ControlledGame().spec)
        settings = EmulatorPlanningConfig(
            anchors=2, horizon=3, beam_width=4, proposal_count=2,
            repeats=2, max_actual_steps=96,
        )
        with patch.object(GameEnvironmentRequest, "build",
                          side_effect=lambda **_: ControlledGame()):
            evidence = run_native_confirmed_planning(
                native_request(), model=model, training_report=report,
                rights_acknowledged=True, config=settings,
            )
        self.assertEqual(evidence["source_anchors"], 2)
        self.assertEqual(evidence["tested_plan_count"], 4)
        self.assertEqual(evidence["independent_trial_repetitions"], 2)
        self.assertFalse(evidence["limitations"]["production_jeeves_promotion"])
        self.assertEqual(evidence["limitations"]["neural_or_q_weight_updates"], 0)
        self.assertEqual(len(evidence["physical_evidence"]), 2)
        self.assertTrue(evidence["real_emulator_steps"] > 0)
        for anchor in evidence["physical_evidence"]:
            self.assertEqual(len(anchor["model_proposals_physically_checked"]), 2)
            for tested in anchor["model_proposals_physically_checked"]:
                self.assertTrue(tested["full_proposed_horizon_executed"])
                self.assertTrue(tested["source_replay_stable"])
                self.assertTrue(tested["baseline_replay_stable"])

    def test_unqualified_neural_gate_or_source_mismatch_refuses_action(self):
        model, report = neural_candidate(ControlledGame().spec)
        report["candidate_status"] = "candidate_failed_heldout_benchmark"
        report["report_digest"] = digest({key: value for key, value in report.items()
                                           if key != "report_digest"})
        with self.assertRaises(EmulatorPlanningError):
            run_native_confirmed_planning(
                native_request(), model=model,
                training_report=report, rights_acknowledged=True,
            )
        model, report = neural_candidate(ControlledGame().spec)
        model["source_environment_digest"] = "a" * 64
        model["model_digest"] = digest({key: value for key, value in model.items()
                                         if key != "model_digest"})
        report["world_model_digest"] = model["model_digest"]
        report["report_digest"] = digest({key: value for key, value in report.items()
                                           if key != "report_digest"})
        with patch.object(GameEnvironmentRequest, "build",
                          side_effect=lambda **_: ControlledGame()):
            with self.assertRaises(EmulatorPlanningError):
                run_native_confirmed_planning(
                    native_request(), model=model,
                    training_report=report, rights_acknowledged=True,
                )

    def test_physical_plan_budget_bound_and_source_rights(self):
        model, report = neural_candidate(ControlledGame().spec)
        with self.assertRaises(EmulatorPlanningError):
            run_native_confirmed_planning(
                native_request(), model=model,
                training_report=report, rights_acknowledged=False,
            )
        with self.assertRaises(EmulatorPlanningError):
            run_native_confirmed_planning(
                native_request(), model=model,
                training_report=report, rights_acknowledged=True,
                config=EmulatorPlanningConfig(
                    anchors=4, horizon=8, repeats=4,
                    proposal_count=6, beam_width=6,
                    max_actual_steps=32,
                ),
            )


if __name__ == "__main__":
    unittest.main()
