"""Actual-game replay experiments, not synthetic or untrusted scenario scoring."""
from __future__ import annotations

from copy import deepcopy
import unittest

from tests.test_game_builder_advanced_interleaved_world import (
    OriginalInterleavedWorldTests as F,
)
from skeleton.ai.game_builder.advanced_interleaved_world import run_interleaved_world
from skeleton.ai.game_builder.advanced_world_counterfactuals import (
    MAX_CANDIDATES,CounterfactualError,derive_counterfactuals,
    run_counterfactual_laboratory,verify_counterfactual_laboratory,
)


class SourceCausalCounterfactualTests(unittest.TestCase):
    @staticmethod
    def setup():
        p,g,scene,settings=F.inputs()
        baseline=F.timeline("physical","genre")
        alternative=F.timeline("genre","physical")
        return p,g,scene,settings,baseline,alternative

    def test_true_causal_order_is_reexecuted_with_real_npc_source_history(self):
        p,g,s,c,baseline,alternative=self.setup()
        originals=deepcopy((p,g,s,c,baseline))
        report=run_counterfactual_laboratory(p,g,s,baseline,[
            {"id":"harvest_before_collision","timeline":alternative},
        ],c)
        self.assertEqual((p,g,s,c,baseline),originals)
        self.assertEqual(report["valid_count"],1)
        self.assertEqual(report["rejected_count"],0)
        self.assertEqual(report["candidate_count"],1)
        trial=report["experiments"][0]
        self.assertEqual(trial["status"],"valid")
        self.assertTrue(trial["difference_from_baseline"]["source_actor_order_changed"])
        self.assertEqual(trial["measured_world"]["source_actor_chronology"],
                         ["external:genre","external:physics"])
        self.assertEqual(report["baseline_world"]["source_actor_chronology"],
                         ["external:physics","external:genre"])
        self.assertEqual(trial["measured_world"]["player_gold"],
                         run_interleaved_world(p,g,s,alternative,c)["world_state"]["gold"])
        self.assertTrue(verify_counterfactual_laboratory(report,p,g,s,baseline,[
            {"id":"harvest_before_collision","timeline":alternative}
        ],c))

    def test_same_true_causes_require_complete_source_order_and_same_action_count(self):
        p,g,s,c,base,other=self.setup()
        result=run_counterfactual_laboratory(p,g,s,base,[
            {"id":"legitimate","timeline":other},
            {"id":"fabricated_missing","timeline":F.timeline("genre")},
        ],c)
        self.assertEqual(result["valid_count"],1)
        self.assertEqual(result["rejected_count"],1)
        self.assertEqual(result["experiments"][1]["status"],
                         "rejected_by_original_game_rules")
        self.assertIsNone(result["experiments"][1]["measured_score"])
        self.assertIsNone(result["experiments"][1]["actual_world_digest"])
        self.assertFalse(result["automatic_world_promotion_approved"])

    def test_clock_derivation_is_repeatable_and_only_swaps_original_events(self):
        p,g,s,c,base,other=self.setup()
        derived=derive_counterfactuals(base,limit=6)
        self.assertEqual(len(derived),1)
        self.assertEqual(derived[0]["timeline"],other)
        self.assertEqual(derived,derive_counterfactuals(base,limit=6))
        self.assertEqual(len(derive_counterfactuals(
            F.timeline("physical","world","genre"))),2)
        result=run_counterfactual_laboratory(p,g,s,base,derived,c)
        self.assertEqual(result["valid_count"],1)

    def test_default_objective_never_invents_better_npc_outcome(self):
        p,g,s,c,base,other=self.setup()
        scenarios=[{"id":"swap","timeline":other}]
        for objective,field in (
            ("preserve_sites","total_site_integrity"),
            ("retain_supplies","player_supplies"),
            ("maximize_earned_quests","quests_completed"),
            ("maximize_firsthand_memories","firsthand_memory_records"),
        ):
            with self.subTest(objective=objective):
                report=run_counterfactual_laboratory(
                    p,g,s,base,scenarios,c,objective=objective)
                expected=max(report["baseline_world"][field],
                             report["experiments"][0]["measured_world"][field])
                self.assertEqual(report["highest_measured_score"],expected)
                # A tie stays with the verified unchanged baseline.
                if report["baseline_score"]==expected:
                    self.assertEqual(report["objective_favorite"],"baseline")
                self.assertTrue(verify_counterfactual_laboratory(
                    report,p,g,s,base,scenarios,c))

    def test_valid_world_wait_permutation_has_real_tick_and_npc_progression(self):
        p,g,s,c,_,_=self.setup()
        base=F.timeline("physical","world","genre")
        variant=F.timeline("world","physical","genre")
        report=run_counterfactual_laboratory(p,g,s,base,[
            {"id":"wait_before_crash","timeline":variant}
        ],c,objective="maximize_firsthand_memories")
        self.assertEqual(report["baseline_world"]["clock_ticks"],3)
        self.assertEqual(report["experiments"][0]["measured_world"]["clock_ticks"],3)
        self.assertEqual(report["valid_count"],1)
        self.assertTrue(verify_counterfactual_laboratory(
            report,p,g,s,base,[{"id":"wait_before_crash","timeline":variant}],c))

    def test_impossible_backdating_is_a_rejected_hypothesis_not_a_success(self):
        p,g,s,c,base,other=self.setup()
        bad=deepcopy(other)
        bad[1]["source_index"]=900
        result=run_counterfactual_laboratory(p,g,s,base,[
            {"id":"impossible_source","timeline":bad}
        ],c)
        self.assertEqual(result["valid_count"],0)
        self.assertEqual(result["rejected_count"],1)
        self.assertEqual(result["objective_favorite"],"baseline")
        self.assertIsNotNone(result["experiments"][0]["reason"])

    def test_invalid_baseline_clock_is_rejected_not_laundered_by_scenarios(self):
        p,g,s,c,base,other=self.setup()
        invalid=deepcopy(base)
        invalid[0]["at"]=1
        with self.assertRaises(CounterfactualError):
            run_counterfactual_laboratory(p,g,s,invalid,[
                {"id":"valid_but_wrong_baseline","timeline":other}
            ],c)
        bad=deepcopy(base)
        bad[0]["source_index"]=45
        with self.assertRaises(CounterfactualError):
            run_counterfactual_laboratory(p,g,s,bad,[
                {"id":"valid_alternative","timeline":other}
            ],c)

    def test_malformed_cases_and_repeated_schedules_cannot_fake_independent_trials(self):
        p,g,s,c,base,other=self.setup()
        cases=(
            [{"id":"same_baseline","timeline":base}],
            [{"id":"one","timeline":other},{"id":"two","timeline":other}],
            [{"id":"BAD NAME","timeline":other}],
            [{"id":"incomplete"}],
            [{"id":"x","timeline":[]}],
            [{"id":"x","timeline":other,"score":9999}],
            [{"id":"x","timeline":[{"at":0,"lane":"physical","source_index":0}]}],
            [{"id":"x","timeline":other}]*2,
        )
        for item in cases:
            with self.subTest(item=item),self.assertRaises(CounterfactualError):
                run_counterfactual_laboratory(p,g,s,base,item,c)
        with self.assertRaises(CounterfactualError):
            run_counterfactual_laboratory(p,g,s,base,[],c)
        with self.assertRaises(CounterfactualError):
            run_counterfactual_laboratory(p,g,s,base,[
                {"id":str(i),"timeline":other} for i in range(MAX_CANDIDATES+1)
            ],c)
        with self.assertRaises(CounterfactualError):
            derive_counterfactuals(base,limit=True)

    def test_recomputed_score_npc_memory_and_receipt_forgeries_fail(self):
        p,g,s,c,base,other=self.setup()
        cases=[{"id":"real_order","timeline":other}]
        verified=run_counterfactual_laboratory(p,g,s,base,cases,c)
        changes=(
            lambda x:x["experiments"][0]["measured_world"].update(player_gold=999),
            lambda x:x["experiments"][0].update(measured_score=999),
            lambda x:x["experiments"][0]["difference_from_baseline"]
                      .update(firsthand_memory_records=99),
            lambda x:x["experiments"][0].update(head_hash="0"*64),
            lambda x:x.update(objective_favorite="fabricated"),
            lambda x:x.update(automatic_world_promotion_approved=True),
            lambda x:x.update(valid_count=999),
            lambda x:x["baseline_world"].update(player_reputation=999),
        )
        for mutate in changes:
            fake=deepcopy(verified)
            mutate(fake)
            with self.assertRaises(CounterfactualError):
                verify_counterfactual_laboratory(fake,p,g,s,base,cases,c)

    def test_changed_original_game_state_never_becomes_counterfactual_fact(self):
        p,g,s,c,base,other=self.setup()
        fake=deepcopy(g)
        fake[0]["source_session"]["state"]["harvested"]=999
        with self.assertRaises(CounterfactualError):
            run_counterfactual_laboratory(p,fake,s,base,[
                {"id":"counterfeit_harvest","timeline":other}
            ],c)


if __name__=="__main__":
    unittest.main()
