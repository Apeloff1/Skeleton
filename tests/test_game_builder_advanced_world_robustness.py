"""Adversarial multi-world robustness of actual original cross-engine causality."""
from __future__ import annotations

from copy import deepcopy
import unittest

from tests import test_game_builder_advanced_interleaved_world as fixtures
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_world_whatif_lab import run_world_whatif
from skeleton.ai.game_builder.advanced_world_robustness import (
    SCHEMA,WorldRobustnessError,
    run_world_robustness,verify_world_robustness,
)


class OriginalWorldRobustnessTests(unittest.TestCase):
    @staticmethod
    def case():
        physical,genres,scene,config=fixtures.OriginalInterleavedWorldTests.inputs()
        schedule=fixtures.OriginalInterleavedWorldTests.timeline(
            "physical","world","genre","world")
        different=make_advanced_scene("quest_director",config,seed=1)
        whatif=run_world_whatif(
            physical,genres,scene,schedule,config,
            max_depth=1,max_attempts=3,max_accepted=2)
        assert whatif["accepted_scenarios"],"real alternative source order required"
        return physical,genres,[scene,different],config,whatif

    def test_real_independent_contexts_preserve_original_source_and_npc_evidence(self):
        p,g,worlds,cfg,whatif=self.case()
        original=deepcopy((p,g,worlds,cfg,whatif))
        proof=run_world_robustness(p,g,worlds,whatif,cfg,max_candidates=1)
        self.assertEqual((p,g,worlds,cfg,whatif),original)
        self.assertEqual(proof["schema"],SCHEMA)
        self.assertEqual(len(proof["world_scenes"]),2)
        self.assertEqual(len(set(proof["world_scenes"])),2)
        self.assertEqual(proof["world_scenes"][0],worlds[0]["digest"])
        self.assertEqual(len(proof["baseline_worlds"]),2)
        self.assertGreaterEqual(proof["evaluated_candidates"],1)
        self.assertEqual(
            len(proof["fully_replayed_candidates"])+len(proof["rejected_candidates"]),
            proof["evaluated_candidates"])
        self.assertTrue(verify_world_robustness(
            proof,p,g,worlds,whatif,cfg))

    def test_no_one_scene_win_masquerades_as_improvement_for_all_contexts(self):
        p,g,worlds,cfg,whatif=self.case()
        proof=run_world_robustness(p,g,worlds,whatif,cfg,max_candidates=2)
        for scenario in proof["fully_replayed_candidates"]:
            self.assertEqual(len(scenario["context_comparisons"]),2)
            self.assertEqual(
                scenario["strict_improvement_in_every_authored_context"],
                all(item["outperforms_baseline"]
                    for item in scenario["context_comparisons"]))
            self.assertEqual(
                scenario["not_worse_in_any_authored_context"],
                all(item["does_not_underperform_baseline"]
                    for item in scenario["context_comparisons"]))
        selected=next((s for s in proof["fully_replayed_candidates"]
                       if s["scenario_id"]==proof["selected_scenario_id"]),None)
        self.assertEqual(
            proof["selected_strictly_improves_every_context"],
            selected["strict_improvement_in_every_authored_context"]
            if selected else False)
        self.assertFalse(proof["population_generalization_claimed"])
        self.assertFalse(proof["automatic_ai_weights_promoted"])

    def test_only_original_earned_eyewitnesses_survive_cross_climate_replay(self):
        p,g,worlds,cfg,whatif=self.case()
        report=run_world_robustness(p,g,worlds,whatif,cfg,max_candidates=1)
        for baseline in report["baseline_worlds"]:
            self.assertTrue(baseline["campaign_digest"])
            self.assertGreater(baseline["metrics"]["world_tick"],0)
            self.assertEqual(
                baseline["metrics"]["direct_memories"],
                sum(len(n["direct"]) for n in baseline["original_npc_memories"]))
            for item in baseline["direct_source_events"]:
                self.assertIn(item["lane"],("physical","genre"))
                self.assertIsInstance(item["source_receipt"],str)
                self.assertIsInstance(item["firsthand_witnesses"],list)

    def test_selected_worst_case_is_grounded_in_genuine_replayed_worlds(self):
        p,g,worlds,cfg,whatif=self.case()
        report=run_world_robustness(p,g,worlds,whatif,cfg,max_candidates=2)
        if not report["fully_replayed_candidates"]:
            self.assertIsNone(report["selected_scenario_id"])
            self.assertFalse(report["selected_beats_worst_baseline"])
            return
        selected=report["fully_replayed_candidates"][0]
        self.assertEqual(report["selected_scenario_id"],selected["scenario_id"])
        expected=min(tuple(x["objective_score"])
                     for x in selected["context_outcomes"])
        self.assertEqual(report["selected_worst_observed_score"],list(expected))
        self.assertEqual(
            report["selected_beats_worst_baseline"],
            expected>tuple(report["worst_baseline_score"]))

    def test_duplicate_wrong_first_and_fabricated_world_scenes_fail(self):
        p,g,worlds,cfg,whatif=self.case()
        for scenes in (
            worlds[:1],[worlds[0],worlds[0]],
            list(reversed(worlds)),
            worlds+[make_advanced_scene("quest_director",cfg,seed=2),
                    make_advanced_scene("quest_director",cfg,seed=3)],
        ):
            with self.subTest(count=len(scenes)),self.assertRaises(WorldRobustnessError):
                run_world_robustness(p,g,scenes,whatif,cfg)
        changed=deepcopy(worlds)
        changed[1]["seed"]=400
        with self.assertRaises(WorldRobustnessError):
            run_world_robustness(p,g,changed,whatif,cfg)

    def test_bad_candidate_ceilings_and_boolean_parameter_are_rejected(self):
        p,g,worlds,cfg,whatif=self.case()
        for budget in (0,-1,5,True,"2",2.0):
            with self.subTest(budget=budget),self.assertRaises(WorldRobustnessError):
                run_world_robustness(p,g,worlds,whatif,cfg,
                                     max_candidates=budget)

    def test_fake_multi_world_improvement_memory_quests_or_certification_denied(self):
        p,g,worlds,cfg,whatif=self.case()
        good=run_world_robustness(p,g,worlds,whatif,cfg,max_candidates=1)
        variants=(
            lambda x:x["baseline_worlds"][1]["metrics"].update(
                     direct_memories=999),
            lambda x:x.update(selected_strictly_improves_every_context=not good["selected_strictly_improves_every_context"]),
            lambda x:x.update(selected_beats_worst_baseline=not good["selected_beats_worst_baseline"]),
            lambda x:x.update(population_generalization_claimed=True),
            lambda x:x.update(automatic_ai_weights_promoted=True),
            lambda x:x["baseline_worlds"][0]["direct_source_events"][0]
                     .update(firsthand_witnesses=[999]),
            lambda x:x.update(digest="0"*64),
        )
        for mutate in variants:
            forged=deepcopy(good);mutate(forged)
            with self.assertRaises(WorldRobustnessError):
                verify_world_robustness(forged,p,g,worlds,whatif,cfg)

    def test_unsigned_genre_achievement_does_not_become_cross_context_success(self):
        p,g,worlds,cfg,whatif=self.case()
        forged=deepcopy(g)
        forged[0]["source_session"]["state"]["harvested"]=999
        with self.assertRaises(WorldRobustnessError):
            run_world_robustness(p,forged,worlds,whatif,cfg,max_candidates=1)


if __name__=="__main__":
    unittest.main()
