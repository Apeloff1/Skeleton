"""Executable emulator-equivalent studio learning and real Q-update regression."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import ENGINES
from skeleton.jeeves.game_studio_environment import (
    StudioEnvironmentError, StudioGameEnvironment,
    make_studio_source, studio_request_tree,
)
from skeleton.jeeves.game_learning import GameLearningConfig, GamePolicyLearner
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.jeeves.game_studio_policy_cli import train_studio_policy


class StudioLearningTests(unittest.TestCase):
    def _request(self, engine="economy", actions=("inspect", "wait", "survey")):
        return GameEnvironmentRequest(
            "studio:" + engine, kind="studio", max_steps=8,
            tree=studio_request_tree(make_studio_source(engine, actions=actions)),
        )

    def test_all_registered_studio_engines_have_emulator_protocol(self):
        for editor in ENGINES:
            with self.subTest(editor=editor):
                env = self._request(editor, ("inspect",) if "inspect" in
                                    StudioGameEnvironment(
                                        make_studio_source(editor)
                                    ).actions else
                                    (make_studio_source(editor)["actions"][0],)).build()
                obs = env.reset(2**50 + 13)
                self.assertEqual(set(obs), set(env.spec.observation_bins))
                self.assertEqual(env.spec.environment_id, "studio:" + editor)
                self.assertEqual(env.snapshot(), env.snapshot())
                self.assertFalse(env.descriptor["production_neural_weights_modified"])
                env.close()

    def test_snapshot_restore_does_not_accept_forged_money(self):
        request = self._request()
        env = request.build()
        env.reset(1042)
        move = env.step("inspect")
        self.assertEqual(set(move.reward_components), set(env.spec.reward_components))
        self.assertEqual(move.info["evidence"]["accepted"], True)
        saved = env.snapshot()
        other = request.build()
        restored = other.restore(saved)
        self.assertEqual(dict(restored), dict(move.observation))
        self.assertEqual(saved, other.snapshot())
        forged = deepcopy(saved)
        forged["observation"]["score"] += 5000
        with self.assertRaises(StudioEnvironmentError):
            other.restore(forged)
        env.close()
        other.close()

    def test_bad_world_actions_truncate_without_faking_state(self):
        env = self._request(actions=("sell:5", "inspect")).build()
        env.reset(7)
        original = env.snapshot()
        step = env.step("sell:5")
        self.assertTrue(step.truncated)
        self.assertLess(step.reward_components["invalid"], 0)
        self.assertEqual(env.snapshot()["source_session_digest"],
                         original["source_session_digest"])
        clone = self._request(actions=("sell:5", "inspect")).build()
        clone.restore(env.snapshot())
        self.assertEqual(clone.snapshot(), env.snapshot())

    def test_actual_game_episodes_change_policy_weights(self):
        request = self._request()
        env = request.build()
        learner = GamePolicyLearner(
            env.spec, GameLearningConfig(seed=13, max_episodes=4, max_updates=40),
            policy_id="test-studio-economy",
            source_lineage={"rights_acknowledged": True, "original_project": "fixture"},
        )
        before = learner.snapshot()
        trained = learner.train(request.build, episodes=2)
        self.assertEqual(trained.updates, sum(row["steps"] for row in trained.traces))
        self.assertGreater(trained.updates, 0)
        self.assertNotEqual(before["snapshot_digest"], trained.snapshot["snapshot_digest"])
        self.assertEqual(len(trained.traces), 2)
        self.assertTrue(all(entry["environment"]["environment_digest"] ==
                            env.spec.environment_digest for entry in trained.traces))
        env.close()

    def test_measured_player_actions_feed_same_actual_policy_optimizer(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "played.json"
            report = train_studio_policy(
                editor="economy", output=output, authorized=True,
                rights_cleared=True, episodes=2, max_steps=5,
                seed=9, actions=("inspect", "wait", "survey"),
                played_actions=("inspect", "survey", "wait"),
                consent_ref="operator-consent:demo-9",
            )
            candidate = json.loads(output.read_text())
            self.assertEqual(report["episodes"], 3)
            self.assertEqual(report["played_action_q_updates"], 3)
            self.assertEqual(candidate["played_action_q_updates"], 3)
            self.assertIsNotNone(candidate["demonstration_digest"])
            self.assertEqual(candidate["actual_q_updates"], report["q_updates"])
            with self.assertRaises(ValueError):
                train_studio_policy(
                    editor="economy", output=Path(folder) / "bad.json",
                    authorized=True, rights_cleared=True,
                    played_actions=("inspect",),
                )

    def test_candidate_only_training_is_authority_gated(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "candidate.json"
            with self.assertRaises(PermissionError):
                train_studio_policy(editor="economy", output=output,
                                    authorized=False, rights_cleared=True)
            report = train_studio_policy(
                editor="economy", output=output, authorized=True,
                rights_cleared=True, episodes=2, max_steps=5, seed=6,
                actions=("inspect", "wait", "survey"),
            )
            doc = json.loads(output.read_text())
            self.assertGreater(report["q_updates"], 0)
            self.assertFalse(doc["production_neural_weights_modified"])
            self.assertFalse(doc["automatic_promotion"])
            self.assertEqual(doc["actual_q_updates"], report["q_updates"])
            with self.assertRaises(FileExistsError):
                train_studio_policy(editor="economy", output=output,
                                    authorized=True, rights_cleared=True,
                                    episodes=2, max_steps=5)


if __name__ == "__main__":
    unittest.main()
