"""Typed objectives and fail states over the real Director and encounter runtimes."""
from __future__ import annotations

from collections import deque
from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_encounter_runtime import (
    EncounterSpec, demonstrate_encounter, encounter_play,
)
from skeleton.ai.game_builder.quest_fail_states import (
    FailCondition, evaluate_failures, failed_quests,
)
from skeleton.ai.game_builder.quest_objectives import (
    DIRECTOR_KIND, ObjectiveKind, TypedObjective, objective_progress,
    objectives_from_records, quest_progress, to_solution,
)
from skeleton.ai.game_builder.quest_scene_engine import (
    ACTION_TYPES, DirectorAction, director_initial, director_play, director_step,
    director_verify, quest_methods,
)
from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.frontier.progression.quests import initialize_progress, quest_from_record

ROUTE = ((1, 1), (2, 1), (3, 1), (4, 1), (4, 2))


def world():
    return forge_director(
        "scene_rpg", seed=10817,
        regions=tuple(f"region_{i:02d}" for i in range(12)),
        quest_types=("main_story", "escort_leash", "combat", "investigation"),
        stages=3,
    )


def travel_to(w, state, dest):
    graph = {s.key: s.links for s in w.scenes}
    search, seen = deque([(state.scene, ())]), {state.scene}
    while search:
        cur, path = search.popleft()
        if cur == dest:
            return path
        for n in graph[cur]:
            if n not in seen:
                seen.add(n)
                search.append((n, (*path, n)))
    raise AssertionError("disconnected")


class ObjectiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = world()

    def test_every_kind_maps_to_a_director_action_type(self):
        self.assertEqual(set(DIRECTOR_KIND), set(ObjectiveKind))
        for kind in ObjectiveKind:
            self.assertIn(kind.director_kind, ACTION_TYPES)
            p = TypedObjective(kind, "ancient_gate", 2).to_parameter()
            self.assertEqual((p.kind, p.target, p.count), (kind.director_kind, "ancient_gate", 2))

    def test_solution_and_frontier_record_round_trip(self):
        objs = (TypedObjective("kill", "wolf", 3), TypedObjective("collect", "herb", 2))
        sol = to_solution("hunt", objs, creativity=1, outcome_flag="path_hunter")
        self.assertEqual([p.kind for p in sol.required], ["fight", "gather"])
        spec = quest_from_record({"id": "q1", "name": "Hunt", "type": "side",
                                  "objectives": [o.to_spec_record() for o in objs]})
        self.assertEqual(objectives_from_records(spec.objectives), objs)
        self.assertEqual(initialize_progress(spec).objectives["0"].target, 3)

    def test_invalid_objectives_rejected(self):
        with self.assertRaises(ValueError):
            TypedObjective("loot", "x")
        with self.assertRaises(Exception):
            TypedObjective("kill", "Bad Target")
        with self.assertRaises(Exception):
            TypedObjective("kill", "wolf", 0)
        spec = EncounterSpec(key="walk", kind="escort_path", path=ROUTE)
        with self.assertRaises(ValueError):
            TypedObjective("kill", "wolf", encounter=spec)

    def test_progress_projects_records_from_real_director_play(self):
        w = self.w
        q, st = w.quests[0], w.quests[0].stages[0]
        state, acts = director_initial(w), []
        for link in travel_to(w, state, st.scene_ids[0]):
            a = DirectorAction("travel", link, state.scene)
            state = director_step(w, state, a)
            acts.append(a)
        method = quest_methods(w, q.key, st.key)[0]
        for a in method:
            state = director_step(w, state, a)
            acts.append(a)
        proof = director_play(w, acts)
        director_verify(w, proof)
        req = st.solutions[0].required[0]
        # The forged stage uses a non-typed kind; relabel its real record as talk.
        sig = f"{req.kind}:{req.target}"
        self.assertTrue(any(r[2] == sig for r in proof.final.records))
        talk = TypedObjective("talk", req.target, req.count)
        fake = replace(proof.final, records=tuple(
            (a, b, "talk:" + c.split(":", 1)[1] if c == sig else c, n)
            for a, b, c, n in proof.final.records))
        prog = objective_progress(fake, q.key, st.key, [talk])
        self.assertTrue(prog["0"].completed)
        self.assertEqual(quest_progress(q.key, prog).status, "completed")
        empty = objective_progress(director_initial(w), q.key, st.key, [talk])
        self.assertEqual(empty["0"].current, 0)
        self.assertEqual(quest_progress(q.key, empty).status, "active")

    def test_escort_needs_a_verified_won_encounter(self):
        spec = EncounterSpec(key="walk", kind="escort_path", path=ROUTE)
        esc = TypedObjective("escort", "caravan", 1, encounter=spec)
        base = director_initial(self.w)
        st = replace(base, records=(("q", "s", "escort_follow:caravan", 1),))
        self.assertFalse(objective_progress(st, "q", "s", [esc])["0"].completed)
        won = demonstrate_encounter(spec, authorized=True)
        self.assertEqual(won.final.status, "won")
        self.assertTrue(objective_progress(st, "q", "s", [esc], escorts={0: won})["0"].completed)
        forged = replace(won, actions=won.actions[:-1])
        with self.assertRaises(Exception):
            objective_progress(st, "q", "s", [esc], escorts={0: forged})


class FailStateTests(unittest.TestCase):
    def setUp(self):
        self.base = director_initial(world())

    def test_turn_limit_and_flag_fail_incomplete_quests_only(self):
        st = replace(self.base, turn=12, narrative_flags=("path_rival",))
        conds = [FailCondition("q1", "turn_limit", limit=10),
                 FailCondition("q2", "flag", flag="path_rival"),
                 FailCondition("q3", "turn_limit", limit=20)]
        self.assertEqual(failed_quests(evaluate_failures(st, conds)), {"q1", "q2"})
        done = replace(st, complete=("q1",))
        self.assertEqual(failed_quests(evaluate_failures(done, conds)), {"q2"})
        self.assertEqual(quest_progress("q1", {}, failed=True).status, "failed")

    def test_lost_escort_encounter_fails_quest(self):
        spec = EncounterSpec(key="walk", kind="escort_path", path=ROUTE, deadline=4)
        lost = encounter_play(spec, ("wait",) * 4, authorized=True)
        self.assertEqual(lost.final.status, "lost")
        cond = [FailCondition("q", "escort_lost", encounter=spec)]
        self.assertEqual(failed_quests(evaluate_failures(self.base, cond, escorts={"walk": lost})), {"q"})
        self.assertEqual(evaluate_failures(self.base, cond), ())

    def test_bad_conditions_rejected(self):
        for kw in ({"kind": "abandon"}, {"kind": "turn_limit"}, {"kind": "flag"},
                   {"kind": "escort_lost"}):
            with self.assertRaises(ValueError):
                FailCondition("q", **kw)


if __name__ == "__main__":
    unittest.main()
