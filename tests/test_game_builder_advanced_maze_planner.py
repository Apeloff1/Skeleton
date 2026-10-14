"""AI maze rehearsal proves only actual exits, never imaginary connectivity."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_maze_runtime import default_layout,TOPOLOGIES
from skeleton.ai.game_builder.advanced_maze_planner import (
    MazePlanningError,plan_original_maze,verify_original_maze_plan,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.system_editors import make_editor_document


class MazePlannerTests(unittest.TestCase):
    @staticmethod
    def source(topology="grid"):
        settings=dict(width=7,height=7,levels=1,key_count=1,
                      hazards=0,wall_budget=0,topology=topology)
        cfg=make_editor_document("maze",settings)["settings"]
        scene=make_advanced_scene("maze",settings,layout=default_layout(cfg,0))
        return settings,scene

    def test_true_grid_exit_requires_all_physical_source_authority(self):
        cfg,scene=self.source()
        result=plan_original_maze(scene,cfg,max_states=12000,
                                  max_depth=32,beam_width=96)
        self.assertEqual(result["status"],"replay_verified_exit")
        self.assertEqual(result["actual_keys"],1)
        self.assertTrue(result["independent_replay_verified"])
        self.assertFalse(result["native_hardware_certified"])
        self.assertFalse(result["publication_certified"])
        self.assertTrue(verify_original_maze_plan(result,scene,cfg))
        proof=run_advanced_session("maze",cfg,result["actions"],
                                   seed=scene["seed"],scene=scene)
        self.assertTrue(proof["state"]["finished"])
        self.assertTrue(verify_advanced_session(proof,cfg))
        self.assertEqual(result["gameplay_receipt_digest"],proof["digest"])

    def test_small_search_is_never_a_claim_of_world_impossibility(self):
        cfg,scene=self.source("moving")
        result=plan_original_maze(scene,cfg,max_states=8,max_depth=2,
                                  beam_width=2)
        self.assertEqual(result["status"],"inconclusive_bounded_search")
        self.assertFalse(result["independent_replay_verified"])
        self.assertFalse(result["exhaustive_search_proved"])
        self.assertEqual(result["actions"],[])
        self.assertTrue(verify_original_maze_plan(result,scene,cfg))

    def test_forged_routes_and_unbounded_search_cannot_promote(self):
        cfg,scene=self.source()
        receipt=plan_original_maze(scene,cfg,max_states=8,
                                   max_depth=2,beam_width=2)
        for tweak in (
            lambda x:x.update(status="replay_verified_exit"),
            lambda x:x.update(source_digest="f"*64),
            lambda x:x.update(best_partial_health=9999),
            lambda x:x.update(max_states=9),
            lambda x:x.update(digest="x"),
        ):
            altered=deepcopy(receipt);tweak(altered)
            with self.assertRaises(MazePlanningError):
                verify_original_maze_plan(altered,scene,cfg)
        for budgets in (
            {"max_states":True},{"max_states":30001},
            {"beam_width":0},{"max_depth":129},
        ):
            with self.assertRaises(MazePlanningError):
                plan_original_maze(scene,cfg,**budgets)


if __name__=="__main__":
    unittest.main()
