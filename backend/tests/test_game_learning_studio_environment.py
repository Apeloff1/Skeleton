"""Application project routing for original studio engines (no live Mongo needed)."""
from __future__ import annotations
import unittest

from core.game_learning import GameLearningWorkspace, GameLearningError
from skeleton.jeeves.game_studio_environment import (
    make_studio_source, studio_request_tree,
)
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest


class AuthoredStudioEnvironmentTests(unittest.TestCase):
    def test_source_is_selected_without_emulator_spoof(self):
        tree = studio_request_tree(make_studio_source("economy"))
        kind = GameLearningWorkspace.authored_environment_kind(tree)
        self.assertEqual(kind, "studio")
        target = GameLearningWorkspace.authored_runtime_target(tree, kind, "eight_bit")
        self.assertEqual(target, "studio:economy")
        trimmed = GameLearningWorkspace.authored_runtime_tree(tree, kind)
        request = GameEnvironmentRequest(target, tree=trimmed, kind=kind, max_steps=16)
        env = request.build()
        env.reset(22)
        self.assertEqual(env.spec.environment_id, "studio:economy")
        self.assertEqual(env.step("inspect").info["evidence"]["accepted"], True)

    def test_competing_authoritative_game_sources_are_rejected(self):
        tree = studio_request_tree(make_studio_source("narrative"))
        tree["game/successor/spec.json"] = "{}"
        with self.assertRaises(GameLearningError):
            GameLearningWorkspace.authored_environment_kind(tree)
        tree.pop("game/successor/spec.json")
        tree["game/generated/game.json"] = "{}"
        with self.assertRaises(GameLearningError):
            GameLearningWorkspace.authored_environment_kind(tree)


if __name__ == "__main__":
    unittest.main()
