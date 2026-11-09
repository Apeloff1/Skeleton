"""Jeeves/Dragon E2E observation: actual source execution and fail-closed projection.

Offline tests exercise real original playable world creation, replay,
render/package and mirror proof. They do NOT claim local LLM, video capture,
Godot binary execution, human playtesting, or production model training.
"""
from __future__ import annotations

import json
import unittest
from copy import deepcopy
from hashlib import sha256

from skeleton.ai.game_builder.studio_e2e_observation import (
    StudioObservationError, observe_goal, observe_tool_execution,
)


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def sample_goal():
    a, b = digest("step-a"), digest("step-b")
    return {
        "schema_version": "skeleton.game.studio_goal.v2",
        "goal_id": "jeeves-e2e-001",
        "project_id": "original-001",
        "status": "completed",
        "history_digest": b,
        "completion_requirements": ["edit", "simulate"],
        "completion": {"verified": False},
        "recovery": {"next_action": "inspect"},
        "steps": [
            {
                "index": 0, "previous_step_digest": digest("history-root"),
                "step_digest": a, "executed": True,
                "decision": {"operation": "world.edit", "raw_prompt": "SECRET-DO-NOT-EXPOSE"},
                "model_receipt": {"raw_response": "PRIVATE-MODEL-OUTPUT"},
                "result": {"private_file": "SECRET-SOURCE-CODE"},
            },
            {
                "index": 1, "previous_step_digest": a,
                "step_digest": b, "executed": True,
                "decision": {"operation": "simulate"},
                "model_receipt": {"output_digest": digest("model-2")},
                "result": {"private_policy": "DO-NOT-EXPORT"},
            },
        ],
    }


class JeevesDragonObservationTests(unittest.TestCase):
    def test_goal_projection_is_digest_chained_and_never_leaks_prompt_or_source(self):
        full = observe_goal(sample_goal(), after=0, limit=2)
        self.assertEqual(full["total_observations"], 4)
        self.assertEqual(full["actions_executed"], 2)
        self.assertEqual(full["observed_stages"]["authoring"], 1)
        self.assertEqual(full["observed_stages"]["playthrough"], 1)
        self.assertFalse(full["workflow_requirements_verified"])
        self.assertFalse(full["game_qualified"])
        self.assertEqual(full["dragon_learning"]["model_training"], "not_authorized")
        self.assertEqual(full["dragon_learning"]["screen_video"], "not_captured")
        prev = None
        for event in full["observations"]:
            self.assertEqual(len(event["event_digest"]), 64)
            self.assertNotIn("SECRET", json.dumps(event))
            self.assertNotIn("PRIVATE", json.dumps(event))
            if prev:
                self.assertEqual(event["previous_event_digest"], prev)
            prev = event["event_digest"]
        self.assertNotIn("DO-NOT-EXPORT", json.dumps(full))
        self.assertNotIn("raw_response", json.dumps(full))

    def test_pagination_and_replay_identity_are_stable(self):
        goal = sample_goal()
        first = observe_goal(goal, after=0, limit=1)
        second = observe_goal(goal, after=1, limit=1)
        again = observe_goal(goal, after=1, limit=1)
        self.assertEqual(first["next_cursor"], 1)
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(second, again)
        self.assertEqual(first["observations"][-1]["event_digest"],
                         second["observations"][0]["previous_event_digest"])
        self.assertEqual(first["head_event_digest"], second["head_event_digest"])
        self.assertEqual(first["steps_observed"], 2)

    def test_terminal_status_and_step_counts_do_not_fabricate_completion(self):
        goal = sample_goal()
        goal["completion"] = {"verified": False}
        self.assertFalse(observe_goal(goal)["workflow_requirements_verified"])
        goal["status"] = "planned"
        goal["steps"][1]["executed"] = False
        row = observe_goal(goal)
        self.assertEqual(row["actions_executed"], 1)
        self.assertEqual(row["observations"][-1]["kind"], "builder.non_execution_observed")
        self.assertEqual(row["observed_stages"]["playthrough"], 0)

    def test_history_corruption_fail_closed(self):
        goal = sample_goal()
        for mutate in (
            lambda x: x.update(schema_version="skeleton.game.studio_goal.v1"),
            lambda x: x.update(history_digest=digest("wrong-head")),
            lambda x: x["steps"][1].update(previous_step_digest=digest("wrong-parent")),
            lambda x: x["steps"][1].update(step_digest="bogus"),
            lambda x: x["steps"][0].update(index=True),
            lambda x: x["steps"][0].update(executed="true"),
            lambda x: x["steps"][0]["decision"].update(operation="arbitrary.injection()"),
        ):
            forged = deepcopy(goal)
            mutate(forged)
            with self.subTest(mutate=mutate), self.assertRaises(StudioObservationError):
                observe_goal(forged)

    def test_bounds_legacy_and_empty_journal(self):
        goal = sample_goal()
        for value in (-1, 17, True, "0"):
            with self.subTest(cursor=value), self.assertRaises(StudioObservationError):
                observe_goal(goal, after=value)
        for value in (0, 17, False):
            with self.subTest(limit=value), self.assertRaises(StudioObservationError):
                observe_goal(goal, limit=value)
        empty = sample_goal()
        empty["steps"] = []
        empty["history_digest"] = digest("history-root")
        empty["status"] = "ready"
        result = observe_goal(empty)
        self.assertEqual(result["total_observations"], 0)
        self.assertIsNone(result["head_event_digest"])
        self.assertFalse(result["workflow_requirements_verified"])
        with self.assertRaises(StudioObservationError):
            observe_goal({})

    def test_actual_authorized_builder_world_replay_compilation_and_mirror(self):
        from skeleton.ai.game_builder.contracts import canonical_digest
        from skeleton.ai.game_builder.playable_world import GameBuildIntent
        from skeleton.ai.game_builder.studio_execution_plane import execute_local_tool_plan
        from skeleton.ai.game_builder.studio_tool_fabric import Actor, Phase, ToolFabric, ToolRequest

        intent = GameBuildIntent(
            project_id="dragon-actual-e2e", title="Dragon Real Replay",
            subtitle="Original generated maze with actual replay and mirror.",
            seed=742193, width=11, height=11, levels=1,
            collectibles_per_level=1, hazards_per_level=1,
            starting_health=4, theme="ocean",
        )
        key = canonical_digest(intent.to_payload())
        sequence = (
            (Actor.JEEVES, Phase.ORIGINAL, "world.generate"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "game.simulate"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "game.browser"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "game.godot"),
            (Actor.MIRROR, Phase.REVIEW, "mirror.fuzz"),
        )
        plan = ToolFabric().plan(tuple(
            ToolRequest(actor, phase, name, key, "Authorized E2E local execution")
            for actor, phase, name in sequence
        ), authorized=True)
        with self.assertRaises(PermissionError):
            execute_local_tool_plan(intent, plan, authorized=False)
        outcome = execute_local_tool_plan(intent, plan, authorized=True, mirror_attempts=64)
        self.assertEqual(outcome.project.proof.final_state.status, "won")
        self.assertTrue(outcome.mirror.passed)
        self.assertEqual(len(outcome.receipts), 5)
        observation = observe_tool_execution(outcome)
        self.assertEqual(len(observation["observations"]), 5)
        self.assertEqual(observation["outcome_digest"], outcome.digest)
        self.assertEqual(observation["observations"][-1]["tool_id"], "mirror.fuzz")
        self.assertEqual(observation["head_observation_digest"],
                         observation["observations"][-1]["observation_digest"])
        self.assertFalse(observation["model_or_hardware_certification"])
        self.assertEqual(observation["training"], "not_authorized")
        self.assertTrue(observation["e2e_evidence"]["world_constructed"])
        self.assertTrue(observation["e2e_evidence"]["winning_python_replay"])
        self.assertTrue(observation["e2e_evidence"]["browser_source_compiled"])
        self.assertTrue(observation["e2e_evidence"]["godot_source_generated"])
        self.assertTrue(observation["e2e_evidence"]["adversarial_mirror_passed"])
        self.assertFalse(observation["e2e_evidence"]["source_exported"])
        from dataclasses import replace
        broken = replace(
            outcome, receipts=(outcome.receipts[1], *outcome.receipts[1:])
        )
        with self.assertRaises(StudioObservationError):
            observe_tool_execution(broken)
        with self.assertRaises(StudioObservationError):
            observe_tool_execution({"fake_receipts": ["success"]})


if __name__ == "__main__":
    unittest.main()
