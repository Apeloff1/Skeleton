"""Original parkour route planning only accepts replay-proved course completion."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene,
)
from skeleton.ai.game_builder.advanced_parkour_runtime import default_layout
from skeleton.ai.game_builder.advanced_parkour_planner import (
    ParkourPlanningError, plan_parkour_route, verify_parkour_plan,
)
from skeleton.ai.game_builder.system_editors import make_editor_document


class PlannerProofTests(unittest.TestCase):
    @staticmethod
    def original_clear_route():
        rules=make_editor_document("parkour")["settings"]
        course=default_layout(rules,0)
        for part in course["obstacles"]:
            part["lane"]=0
        return make_advanced_scene("parkour",seed=0,layout=course)

    def test_promotion_requires_genuine_winning_physical_game_replay(self):
        scene=self.original_clear_route()
        plan=plan_parkour_route(scene,max_states=15000,max_depth=64,
                                beam_width=96)
        self.assertEqual(plan["status"],"verified_solution")
        self.assertTrue(plan["independent_original_replay_verified"])
        self.assertFalse(plan["native_hardware_verified"])
        self.assertFalse(plan["publication_certified"])
        self.assertTrue(verify_parkour_plan(plan,scene))
        real=run_advanced_session("parkour",actions=plan["actions"],
                                 scene=scene,seed=scene["seed"])
        self.assertTrue(real["state"]["finished"])
        self.assertTrue(verify_advanced_session(real))
        self.assertEqual(plan["gameplay_receipt_digest"],real["digest"])

    def test_small_search_reports_inconclusive_not_false_impossibility(self):
        scene=self.original_clear_route()
        record=plan_parkour_route(scene,max_states=16,max_depth=2,beam_width=4)
        self.assertEqual(record["status"],"inconclusive_search_budget")
        self.assertFalse(record["exhaustive_search_proved"])
        self.assertFalse(record["independent_original_replay_verified"])
        self.assertTrue(verify_parkour_plan(record,scene))

    def test_forged_solution_evidence_budgets_and_source_rejected(self):
        scene=self.original_clear_route()
        record=plan_parkour_route(scene,max_states=16,max_depth=2,beam_width=4)
        for edit in (
            lambda x:x.update(status="verified_solution"),
            lambda x:x.update(max_states=15000),
            lambda x:x.update(best_partial_health=1000000),
            lambda x:x.update(source_digest="f"*64),
            lambda x:x.update(digest="bad"),
        ):
            changed=deepcopy(record);edit(changed)
            with self.assertRaises(ParkourPlanningError):
                verify_parkour_plan(changed,scene)
        altered=deepcopy(scene)
        altered["digest"]="0"*64
        with self.assertRaises(ValueError):
            plan_parkour_route(altered)

    def test_invalid_state_search_limits_rejected_before_expensive_work(self):
        scene=self.original_clear_route()
        for args in (
            {"max_states":15},{"max_states":50001},{"max_states":True},
            {"max_depth":129},{"beam_width":1},{"beam_width":"100"},
        ):
            with self.assertRaises(ParkourPlanningError):
                plan_parkour_route(scene,**args)


if __name__=="__main__":
    unittest.main()
