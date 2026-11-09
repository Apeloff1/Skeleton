"""Executable multi-solution quest and fully authored scene regressions."""
from __future__ import annotations
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.quest_scene_engine import (
    ARCHETYPES, DirectorError, DirectorAction, director_initial,
    available_director_actions, director_step, director_play, director_verify,
)
from skeleton.ai.game_builder.quest_scene_forge import (
    forge_director, compile_director_blueprint, read_director_blueprint,
)


class QuestSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = forge_director(
            "scene_rpg", seed=10817,
            regions=tuple(f"region_{i:02d}" for i in range(12)),
            quest_types=("main_story", "escort_leash", "combat", "investigation"),
            stages=3,
        )

    def reach(self, world, state, destination):
        from collections import deque
        graph = {s.key: s.links for s in world.scenes}
        search = deque([(state.scene, ())])
        seen = {state.scene}
        while search:
            current, path = search.popleft()
            if current == destination:
                return path
            for neighbor in graph[current]:
                if neighbor not in seen:
                    search.append((neighbor, (*path, neighbor)))
                    seen.add(neighbor)
        raise AssertionError("disconnected game world")

    def stage(self, method, *, optional=False, waiting=0):
        world = self.world
        state = director_initial(world)
        acts = []
        chapter = world.quests[0].stages[0]
        site = chapter.scene_ids[0]
        for link in self.reach(world, state, site):
            act = DirectorAction("travel", link, state.scene)
            state = director_step(world, state, act)
            acts.append(act)
        for _ in range(waiting):
            act = DirectorAction("wait", "wait", state.scene)
            state = director_step(world, state, act)
            acts.append(act)
        criteria = ([] if not optional else list(chapter.optional))
        criteria += list(chapter.solutions[method].required)
        scene = next(x for x in world.scenes if x.key == site)
        for condition in criteria:
            action = next(a for a in scene.affordances
                          if (a.kind, a.target) == (condition.kind, condition.target))
            for _ in range(condition.count):
                act = DirectorAction("use", action.key, state.scene)
                self.assertIn(act, available_director_actions(world, state))
                state = director_step(world, state, act)
                acts.append(act)
        proof = director_play(world, acts)
        director_verify(world, proof)
        self.assertEqual(proof.final, state)
        return state.results[0], proof

    def test_three_real_methods_all_complete_same_stage_with_different_consequences(self):
        outcomes = [self.stage(i)[0] for i in range(3)]
        self.assertEqual([x.approach for x in outcomes],
                         ["method_0", "method_1", "method_2"])
        self.assertEqual(len({x.consequence for x in outcomes}), 3)
        self.assertLess(outcomes[0].creativity_bonus, outcomes[1].creativity_bonus)
        self.assertLess(outcomes[1].creativity_bonus, outcomes[2].creativity_bonus)
        self.assertGreater(outcomes[2].score, outcomes[0].score)

    def test_fast_and_optional_real_conditions_adjust_scored_outcome(self):
        quick, _ = self.stage(1)
        slow, _ = self.stage(1, waiting=8)
        extra, _ = self.stage(1, optional=True)
        self.assertGreater(quick.speed_bonus, slow.speed_bonus)
        self.assertGreater(quick.score, slow.score)
        self.assertEqual(quick.optional_bonus, 0)
        self.assertEqual(extra.optional_bonus, 15)
        self.assertIn("Choice: method_1", extra.lore_entry)

    def test_three_successive_stages_replay_with_real_scene_travel(self):
        world = self.world
        state = director_initial(world)
        history = []
        for stage in world.quests[0].stages:
            site = stage.scene_ids[0]
            for link in self.reach(world, state, site):
                action = DirectorAction("travel", link, state.scene)
                state = director_step(world, state, action)
                history.append(action)
            chosen = stage.solutions[2].required[0]
            scene = next(s for s in world.scenes if s.key == site)
            affordance = next(a for a in scene.affordances
                              if (a.kind, a.target) == (chosen.kind, chosen.target))
            action = DirectorAction("use", affordance.key, state.scene)
            state = director_step(world, state, action)
            history.append(action)
        self.assertEqual(len(state.results), 3)
        self.assertEqual(dict(state.stage_index)["quest_00"], 3)
        self.assertIn("quest_00", state.complete)
        proof = director_play(world, history)
        director_verify(world, proof)
        with self.assertRaises(DirectorError):
            director_verify(world, replace(proof, final=replace(
                proof.final, narrative_flags=("made_up",))))

    def test_every_scene_control_round_trips_through_editable_blueprint(self):
        original = self.world.payload()
        doc = json.loads(json.dumps(original))
        doc["bible"]["invariant_goal"] = "Original shared outcome forever."
        scene = doc["scenes"][0]
        scene["title"] = "Custom bell tower"
        scene["setting"] = "Underground city illuminated by blue lanterns"
        scene["camera"] = "close dolly with upward crane"
        scene["lighting"] = "dynamic azure"
        scene["weather"] = "winter snowfall"
        scene["music"] = "original chamber strings"
        scene["props"] = ["bell", "bridge"]
        scene["cast"] = ["hero", "companion"]
        scene = next(s for s in doc["scenes"] if s["cutscenes"])
        scene["cutscenes"][0]["cues"][0]["value"] = "slow panoramic sunrise"
        rebuilt = compile_director_blueprint(doc, human_reviewed=True)
        self.assertEqual(rebuilt.payload(), doc)
        self.assertNotEqual(rebuilt.digest, self.world.digest)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "full-scene.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            self.assertEqual(
                read_director_blueprint(path, human_reviewed=True).digest,
                rebuilt.digest)

    def test_quest_archetypes_have_actual_non_identical_action_alternatives(self):
        genres = ("main_story", *sorted(ARCHETYPES - {"main_story"}))
        world = forge_director(
            "multi_genre", seed=300, regions=tuple(
                f"zone_{i:02d}" for i in range(24)
            ), quest_types=genres[:30], stages=2,
        )
        self.assertEqual(len(world.quests), 30)
        for quest in world.quests:
            for stage in quest.stages:
                self.assertEqual(len(stage.solutions), 3)
                self.assertEqual(len({s.required[0].kind
                                      for s in stage.solutions}), 3)
                self.assertTrue(stage.cutscene_on_complete)

    def test_no_infinite_loops_script_fields_fake_objectives_or_unreviewed_data(self):
        doc = self.world.payload()
        with self.assertRaises(DirectorError):
            compile_director_blueprint(doc, human_reviewed=False)
        for modification in ("extra", "broken_method", "bad_cue", "broken_region", "dependency_cycle"):
            edited = json.loads(json.dumps(doc))
            if modification == "extra":
                edited["scenes"][0]["external_code"] = "unreviewed"
            elif modification == "broken_method":
                edited["quests"][0]["stages"][0]["solutions"][0]["required"][0][
                    "target"] = "unavailable"
            elif modification == "bad_cue":
                scene = next(s for s in edited["scenes"] if s["cutscenes"])
                scene["cutscenes"][0]["cues"][0]["kind"] = "unsupported"
            elif modification == "broken_region":
                edited["scenes"][0]["links"] = ["not_a_scene"]
            else:
                edited["quests"][0]["requires_quests"] = ["quest_01"]
                edited["quests"][1]["requires_quests"] = ["quest_00"]
            with self.subTest(modification=modification):
                with self.assertRaises(DirectorError):
                    compile_director_blueprint(edited, human_reviewed=True)


if __name__ == "__main__":
    unittest.main()
