"""AI conservation planner certifies only executed, living environmental evidence."""
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_ecosystem_planner import (
    EcologyPlanningError,plan_original_ecology,verify_original_ecology_plan,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)


class EcologicalPlannerTests(unittest.TestCase):
    def test_ai_conservation_is_real_nonterminal_ecological_gameplay(self):
        scene=make_advanced_scene("ecosystem")
        record=plan_original_ecology(scene)
        self.assertEqual(record["status"],"replay_verified_conservation")
        self.assertEqual(record["surveys"],[0,3])
        self.assertTrue(record["world_still_playable"])
        self.assertTrue(record["independent_replay_verified"])
        self.assertFalse(record["native_hardware_verified"])
        self.assertTrue(verify_original_ecology_plan(record,scene))
        proof=run_advanced_session("ecosystem",actions=record["actions"],scene=scene)
        self.assertTrue(proof["state"]["conservation_checkpoint"])
        self.assertTrue(verify_advanced_session(proof))
        self.assertEqual(record["replay_digest"],proof["digest"])

    def test_explicit_retirement_requires_actual_return_to_station(self):
        scene=make_advanced_scene("ecosystem")
        record=plan_original_ecology(scene,retire=True)
        self.assertEqual(record["status"],"replay_verified_conservation")
        self.assertTrue(record["retired"])
        self.assertFalse(record["world_still_playable"])
        self.assertTrue(verify_original_ecology_plan(record,scene))

    def test_unproven_ecological_intervention_is_inconclusive_not_impossible(self):
        scene=make_advanced_scene("ecosystem")
        report=plan_original_ecology(scene,max_actions=2)
        self.assertEqual(report["status"],"inconclusive_bounded_ecology")
        self.assertFalse(report["independent_replay_verified"])
        self.assertFalse(report["exhaustive_search_proved"])
        self.assertTrue(verify_original_ecology_plan(report,scene))

    def test_forged_live_populations_and_nonfinite_budgets_rejected(self):
        scene=make_advanced_scene("ecosystem")
        receipt=plan_original_ecology(scene,max_actions=2)
        for tweak in (
            lambda r:r.update(status="replay_verified_conservation"),
            lambda r:r.update(best_partial_surveys=[0,3]),
            lambda r:r.update(source_digest="a"*64),
            lambda r:r.update(max_actions=3),
            lambda r:r.update(digest="forged"),
        ):
            fake=deepcopy(receipt);tweak(fake)
            with self.assertRaises(EcologyPlanningError):
                verify_original_ecology_plan(fake,scene)
        for values in ({"max_actions":0},{"max_actions":129},
                       {"max_actions":True},{"retire":1}):
            with self.assertRaises(EcologyPlanningError):
                plan_original_ecology(scene,**values)


if __name__=="__main__":
    unittest.main()
