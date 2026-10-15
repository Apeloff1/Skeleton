"""Source-level regression cases for emulator experiment, curriculum and core comparisons.

Synthetic, controlled state machines validate orchestration semantics only.
They do not prove real native library compatibility or run copyrighted ROMs.
"""
import hashlib
import json
import unittest
from unittest.mock import patch

from skeleton.jeeves.game_emulator_curriculum import (
    ANGLES, EvidenceCurriculum, EmulatorCurriculumError,
)
from skeleton.jeeves.game_emulator_experiment_lab import (
    EmulatorExperimentConfig, EmulatorExperimentError,
    MemoryWatch, run_emulator_experiment_matrix,
)
from skeleton.jeeves.game_emulator_cross_core_lab import (
    CrossCoreConfig, EmulatorCrossCoreError, compare_real_emulator_cores,
)
from skeleton.jeeves.game_emulator_host import _measured_signal_channels, _temporal_signal_channels
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.jeeves.game_learning_runtime import GameEnvironmentSpec, EpisodeStep


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ControlledGame:
    def __init__(self, core="fixture", noisy=False):
        self.core = type("Core", (), {"core_id": core, "library_sha256": _digest(["lib", core])})()
        self.spec = GameEnvironmentSpec(
            environment_id="fixture:" + core,
            environment_digest=_digest(["fixture", core]),
            actions=("idle", "a", "b", "left", "right", "up", "down", "start", "select"),
            observation_bins={
                "screen_mean": (0.2, 0.5, 0.8),
                "visual_change": (0.1, 0.5, 0.9),
                "step_fraction": (0.25, 0.5, 0.75),
            },
            reward_components=("visual_change",), max_episode_steps=8,
        )
        self.core_modifier = 1 if core == "gambatte" else 2
        self.noisy = noisy
        self.replays = 0
        self.reset(0)

    def observation(self):
        return {
            "screen_mean": min(1.0, self.value / 20),
            "visual_change": min(1.0, self.value / 16),
            "step_fraction": self.steps / 8,
        }

    def reset(self, seed):
        self.seed = seed
        self.steps = self.value = 0
        self.restore_count = 0
        return self.observation()

    def _advance(self, gain):
        self.steps += 1
        self.value = max(0, min(16, self.value + gain))
        if self.noisy and self.restore_count > 0:
            self.value += self.restore_count % 2
        frame = _digest(["actual native frame", self.core.core_id, self.value, self.steps])
        observation = self.observation()
        return EpisodeStep(
            observation=observation,
            reward_components={"visual_change": observation["visual_change"]},
            terminated=False, truncated=self.steps == 8,
            info={"evidence": {
                "frame_digest": frame,
                "native_runs": self.steps,
                "audio_frames": 0,
                "controller_only": self.controller_only,
                "controller_digest": "e" * 64,
            }},
            transition_digest="",
        )

    def step(self, action):
        self.controller_only = False
        effects = {
            "idle": 0, "a": 2, "b": 1, "left": -1, "right": 2,
            "up": 1, "down": -1, "start": 0, "select": 0,
        }
        return self._advance(effects[action] * self.core_modifier)

    def input_step(self, controls):
        self.controller_only = True
        gain = sum(int(port["buttons"]).bit_count() for port in controls)
        return self._advance(gain * self.core_modifier)

    def snapshot(self):
        state = {"value": self.value, "steps": self.steps, "seed": self.seed}
        return {**state, "state_digest": _digest(state)}

    def restore(self, snapshot):
        state = dict(snapshot)
        claimed = state.pop("state_digest")
        if claimed != _digest(state):
            raise ValueError("corrupt synthetic state")
        self.value, self.steps, self.seed = state["value"], state["steps"], state["seed"]
        self.restore_count += 1
        return self.observation()

    def read_memory(self, region, offset, size):
        return bytes([self.value % 256] * size)

    def close(self):
        pass


def _request(core="gambatte", native=False):
    if native:
        return GameEnvironmentRequest(
            target_id="emulator:game_boy", max_steps=8, kind="libretro",
            core_id=core, registry_digest="a" * 64,
            rom_source=b"rights-cleared synthetic cartridge",
        )
    return GameEnvironmentRequest(
        target_id="game_boy", max_steps=8, kind="builtin",
        rom_source=b"rights-cleared synthetic cartridge",
    )


class SourceExecutedExperimentTests(unittest.TestCase):
    def test_actual_contrast_duration_order_and_repeat_provenance(self):
        config = EmulatorExperimentConfig(
            anchors=2, repeats=2, longest_duration=2,
            max_conditions=8, max_native_steps=96,
        )
        with patch.object(GameEnvironmentRequest, "build",
                          side_effect=lambda **_: ControlledGame()):
            report = run_emulator_experiment_matrix(
                _request(), rights_acknowledged=True, config=config,
            )
        self.assertEqual(report["sampled_anchors"], 2)
        self.assertEqual(report["distinct_conditions"], 8)
        self.assertTrue(report["all_trials_reproducible"])
        self.assertEqual(report["limits"]["weight_updates"], 0)
        self.assertTrue(report["anchors"][0]["analyses"]["action_order"] is not None)
        self.assertTrue(
            report["anchors"][0]["analyses"]["action_effects"]["sustained_input"][
                "mean_observation_distance"
            ] > 0
        )
        self.assertTrue(report["report_digest"])

    def test_memory_watch_only_with_explicit_native_opt_in(self):
        watches = (MemoryWatch("opaque-ram", region=0, offset=0, size=8),)
        config = EmulatorExperimentConfig(
            anchors=1, repeats=2, longest_duration=2, max_conditions=4,
            max_native_steps=32, include_memory_audit=True,
        )
        with patch.object(GameEnvironmentRequest, "build",
                          side_effect=lambda **_: ControlledGame()):
            with self.assertRaises(EmulatorExperimentError):
                run_emulator_experiment_matrix(
                    _request(), rights_acknowledged=True,
                    config=config, watches=watches,
                )
        with patch.object(GameEnvironmentRequest, "build",
                          side_effect=lambda **_: ControlledGame()):
            report = run_emulator_experiment_matrix(
                _request(native=True), rights_acknowledged=True,
                config=config, watches=watches,
            )
        first = report["anchors"][0]["anchored_conditions"][0]["repeats"][0]
        self.assertEqual(first["memory_watches"][0]["bytes"], 8)
        self.assertNotIn("raw_memory", first)

    def test_nonreproducible_state_is_not_marked_stable(self):
        config = EmulatorExperimentConfig(
            anchors=1, repeats=2, longest_duration=2, max_conditions=4,
            max_native_steps=32,
        )
        with patch.object(GameEnvironmentRequest, "build",
                          side_effect=lambda **_: ControlledGame(noisy=True)):
            report = run_emulator_experiment_matrix(
                _request(), rights_acknowledged=True, config=config,
            )
        self.assertFalse(report["all_trials_reproducible"])

    def test_sources_and_resource_limits_fail_closed(self):
        with self.assertRaises(EmulatorExperimentError):
            run_emulator_experiment_matrix(
                _request(), rights_acknowledged=False,
            )
        with self.assertRaises(EmulatorExperimentError):
            run_emulator_experiment_matrix(
                _request(), rights_acknowledged=True,
                config=EmulatorExperimentConfig(
                    anchors=8, longest_duration=16, repeats=5,
                    max_conditions=128, max_native_steps=32,
                ),
            )


class RealSignalSamplingTests(unittest.TestCase):
    def test_temporal_motion_quadrants_and_audio_onset(self):
        previous = bytes(2 * 2 * 3)
        red = bytes([255, 0, 0])
        current = red + bytes(3 * 3)
        sample = _temporal_signal_channels(
            previous, current, 2, 2, b"\x00" * 16,
            b"\xff\x7f\xff\x7f" * 4,
        )
        self.assertEqual(len(sample), 12)
        self.assertEqual(sample["motion_fraction"], 0.25)
        self.assertGreater(sample["motion_quadrant_tl"], 0.99)
        self.assertEqual(sample["motion_quadrant_br"], 0.0)
        self.assertGreater(sample["audio_positive_onset"], 0)
        self.assertTrue(all(0.0 <= val <= 1.0 for val in sample.values()))

    def test_temporal_first_frame_is_measured_not_fabricated(self):
        channels = _temporal_signal_channels(None, bytes(12), 2, 2, b"", b"")
        self.assertEqual(len(channels), 12)
        self.assertTrue(all(x == 0 for x in channels.values()))
        spectral = _measured_signal_channels(bytes(12), 2, 2, [])
        self.assertEqual(len(spectral), 8)


class CurriculumCases(unittest.TestCase):
    def test_mandatory_coverage_and_evidence_scoring(self):
        scheduler = EvidenceCurriculum(("idle", "a", "b"), seed=3)
        for index, angle in enumerate(ANGLES):
            observed, decision = scheduler.select()
            self.assertEqual(observed, angle)
            self.assertEqual(decision["policy"], "mandatory_ten_angle_coverage")
            rows = [{"action": "a"}, {"action": "b"}]
            source = {"trace_digest": _digest(["trace", index]),
                      "return": float(index), "transitions": rows}
            receipt = {
                "trace_digest": source["trace_digest"],
                "actual_steps": 2, "actual_replay_steps": 4,
                "scrutiny_checks": {"check_" + str(n): True for n in range(10)},
                "counterfactual_probes": [
                    {"actual_frame_sha256": "a" * 64},
                    {"actual_frame_sha256": "b" * 64},
                ],
            }
            response = scheduler.observe(
                angle=angle, run_index=index,
                trace=source, receipt=receipt,
                new_signatures=1 if index < 3 else 0,
            )
            self.assertTrue(response["verified_curriculum_digest"])
        selected, decision = scheduler.select()
        self.assertIn(selected, ANGLES)
        self.assertEqual(decision["policy"], "audited_novelty_ucb_with_revisit")
        report = scheduler.report()
        self.assertEqual(report["angle_coverage"], 10)
        self.assertEqual(report["actions"]["a"], 10)
        self.assertFalse(report["limits"]["game_skill_inferred"])

    def test_unsigned_evidence_cannot_drive_training_priorities(self):
        scheduler = EvidenceCurriculum(("idle", "a"))
        with self.assertRaises(EmulatorCurriculumError):
            scheduler.observe(
                angle="exploration", run_index=0,
                trace={"trace_digest": "a" * 64, "transitions": [{"action": "a"}], "return": 1},
                receipt={"actual_steps": 1, "trace_digest": "a" * 64, "scrutiny_checks": {}},
                new_signatures=1,
            )


class CrossCoreCases(unittest.TestCase):
    def test_same_rom_distinct_cores_repeated_and_compared(self):
        requests = [_request("gambatte", native=True), _request("sameboy", native=True)]
        config = CrossCoreConfig(steps=4, repetitions=2, max_native_steps=32)
        def build(request, **kwargs):
            return ControlledGame(core=request.core_id)
        with patch.object(GameEnvironmentRequest, "build", new=build):
            report = compare_real_emulator_cores(
                requests, rights_acknowledged=True, config=config,
                actions=("idle", "a", "right", "b"),
            )
        self.assertEqual(report["actual_native_steps"], 16)
        self.assertEqual(report["compared_approved_native_cores"], 2)
        self.assertTrue(report["all_repeats_stable"])
        self.assertEqual(len(report["cross_core_differences"]), 1)
        self.assertNotEqual(
            report["cross_core_differences"][0]["measured_total_reward_delta"], 0.0,
        )
        self.assertFalse(report["limits"]["pixel_match_proves_hardware_compatibility"])

    def test_cross_core_refuses_cross_rom_and_duplicate_core(self):
        a, b = _request("gambatte", native=True), _request("sameboy", native=True)
        with self.assertRaises(EmulatorCrossCoreError):
            compare_real_emulator_cores(
                [a, a], rights_acknowledged=True,
            )
        c = GameEnvironmentRequest(
            target_id="emulator:game_boy", max_steps=8, kind="libretro",
            core_id="sameboy", registry_digest="a" * 64,
            rom_source=b"DIFFERENT ROM",
        )
        with self.assertRaises(EmulatorCrossCoreError):
            compare_real_emulator_cores([a, c], rights_acknowledged=True)


if __name__ == "__main__":
    unittest.main()
