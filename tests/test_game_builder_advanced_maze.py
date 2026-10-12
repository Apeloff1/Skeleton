"""Five original playable labyrinths: proven exits, real topology and evidence."""
from __future__ import annotations
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_maze_runtime import (
    TOPOLOGIES,ACTIONS,MazeActionError,default_layout,normalize_layout,
    start,step,apply_scene,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ACTION_HELP,ENGINES,AdvancedRuntimeError,
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError,make_advanced_scene,validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editors import (
    catalog,make_editor_document,SystemEditorError,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


class OriginalLabyrinthTests(unittest.TestCase):
    @staticmethod
    def small(topology="grid",levels=1,**extra):
        values=dict(width=7,height=7,levels=levels,hazards=0,
                    wall_budget=0,key_count=1,topology=topology)
        values.update(extra)
        return values

    def test_five_distinct_topologies_are_source_playable(self):
        self.assertIn("maze",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["maze"]))
        spec=next(x for x in catalog() if x["id"]=="maze")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(spec["progression_floor"],"advanced")
        self.assertGreaterEqual(len(spec["fields"]),22)
        self.assertEqual(len(TOPOLOGIES),5)
        for topology in TOPOLOGIES:
            settings=self.small(topology)
            cfg=make_editor_document("maze",settings)["settings"]
            for seed in (0,1,7):
                chart=default_layout(cfg,seed)
                self.assertEqual(normalize_layout(cfg,chart),chart)
                scene=make_advanced_scene("maze",settings,seed=seed)
                self.assertEqual(validate_advanced_scene(scene,settings),scene)
                run=run_advanced_session("maze",settings,seed=seed,scene=scene)
                self.assertTrue(verify_advanced_session(run,settings))
                self.assertFalse(run["publication_certified"])
                self.assertFalse(run["native_hardware_verified"])

    def test_real_original_key_gate_and_exit_for_all_five(self):
        actions=["east","east","east","north","north","north",
                 "open","east","north","finish"]
        for topology in TOPOLOGIES:
            settings=self.small(topology)
            report=run_advanced_session("maze",settings,actions)
            state=report["state"]
            self.assertTrue(state["finished"],topology)
            self.assertFalse(state["failed"],topology)
            self.assertEqual(len(state["collected_keys"]),1)
            self.assertTrue(state["door_open"])
            self.assertEqual(state["position"],[5,5,0])
            self.assertTrue(verify_advanced_session(report,settings))

    def test_multiple_levels_require_real_stairs(self):
        settings=self.small(levels=2)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maze",settings,["ascend"])
        actions=["east","east","east","ascend","north","north",
                 "north","open","east","north","finish"]
        report=run_advanced_session("maze",settings,actions)
        self.assertTrue(report["state"]["finished"])
        self.assertEqual(report["state"]["floor_visits"],[0,1])
        self.assertTrue(verify_advanced_session(report,settings))

    def test_circular_wrap_and_braided_diagonals_are_physical(self):
        circle=run_advanced_session("maze",self.small("circular"),["west"])
        self.assertEqual(circle["state"]["position"],[5,1,0])
        flat=run_advanced_session("maze",self.small("grid"),["west"])
        self.assertEqual(flat["state"]["position"],[1,1,0])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maze",self.small("grid"),["northeast"])
        braided=run_advanced_session("maze",self.small("braided"),["northeast"])
        self.assertEqual(braided["state"]["position"],[2,2,0])
        self.assertTrue(verify_advanced_session(braided,self.small("braided")))

    def test_moving_barrier_requires_a_real_wait_for_phase(self):
        settings=self.small("moving",wall_budget=1)
        cfg=make_editor_document("maze",settings)["settings"]
        layout=default_layout(cfg,0)
        layout["walls"]=[{"at":[2,1,0],"phase":0}]
        layout["keys"]=[[3,1,0]]
        scene=make_advanced_scene("maze",settings,layout=layout)
        blocked=run_advanced_session("maze",settings,["east"],scene=scene)
        self.assertEqual(blocked["state"]["position"],[1,1,0])
        self.assertEqual(blocked["state"]["collisions"],1)
        arrived=run_advanced_session("maze",settings,
                                     ["wait","wait","wait","east"],scene=scene)
        self.assertEqual(arrived["state"]["position"],[2,1,0])
        self.assertEqual(arrived["state"]["phase"],1)
        self.assertTrue(verify_advanced_session(arrived,settings))

    def test_portal_requires_entering_exact_authored_source(self):
        settings=self.small("non_euclidean")
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maze",settings,["warp"])
        correct=run_advanced_session("maze",settings,
                                     ["north","north","north","warp"])
        self.assertEqual(correct["state"]["position"],[4,4,0])
        self.assertEqual(correct["state"]["portal_uses"],1)
        self.assertTrue(verify_advanced_session(correct,settings))

    def test_finite_hazards_and_mirror_replay_reject_forged_keys(self):
        settings=self.small(hazards=1)
        cfg=make_editor_document("maze",settings)["settings"]
        layout=default_layout(cfg,0)
        layout["hazards"]=[[1,2,0]]
        scene=make_advanced_scene("maze",settings,layout=layout)
        hurt=run_advanced_session("maze",settings,["north"],scene=scene)
        self.assertLess(hurt["state"]["health"],cfg["health"])
        self.assertEqual(hurt["state"]["hazard_hits"],1)
        fake=deepcopy(hurt)
        fake["state"]["collected_keys"]=[[2,1,0]]
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(fake,settings)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("maze",settings,["finish"])

    def test_scene_spoofed_portal_gate_and_hazard_fail_closed(self):
        settings=self.small("non_euclidean")
        scene=make_advanced_scene("maze",settings)
        for mutate in (
            lambda m:m["layout"].update(topology="moving"),
            lambda m:m["layout"]["portals"][0].update(destination=[5,5,0]),
            lambda m:m["layout"].update(exit=[2,2,0]),
            lambda m:m["layout"].update(hazards=[[2,2,0]]),
            lambda m:m.update(digest="a"*64),
        ):
            bad=deepcopy(scene);mutate(bad)
            with self.assertRaises(SceneError):
                validate_advanced_scene(bad,settings)

    def test_composite_maze_assembly_has_genuine_source_and_replay(self):
        src=make_editor_document("maze",self.small())
        scene=make_advanced_scene("maze",self.small())
        assembly=compile_system_assembly("original_maze",[src],
                                         authorized=True,scenes=[scene])
        self.assertEqual(assembly["authored_scene_count"],1)
        self.assertEqual(assembly["advanced_runtime_evidence"][0]["editor"],"maze")

    def test_bounded_dimensions_and_keys_cannot_mint_unlimited_state(self):
        for values in (
            {"width":5,"height":5,"levels":1,"key_count":4,"hazards":3},
            {"width":5,"height":5,"levels":1,"topology":"non_euclidean"},
            {"wall_budget":65},{"key_count":0},
            {"stamina":5,"portal_cost":20},
            {"topology":"hyper_portal"},{"health":True},
        ):
            with self.assertRaises(SystemEditorError):
                make_editor_document("maze",values)


if __name__=="__main__":
    unittest.main()
