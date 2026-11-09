"""Original finite procedural world: terrain, survival and chunk persistence."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_procedural_world_runtime import (
    ACTIONS,PERSISTENCE,ProceduralWorldActionError,
    _source_tile,_read,default_layout,normalize_layout,start,step,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES,ACTION_HELP,AdvancedRuntimeError,
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError,make_advanced_scene,validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editors import (
    catalog,make_editor_document,SystemEditorError,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


class OriginalWorldTests(unittest.TestCase):
    def test_generator_supports_three_real_storage_modes(self):
        self.assertIn("procedural_world",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["procedural_world"]))
        self.assertEqual(len(ACTIONS),len(set(ACTIONS)))
        spec=next(s for s in catalog() if s["id"]=="procedural_world")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(spec["progression_floor"],"advanced")
        self.assertGreaterEqual(len(spec["fields"]),30)
        self.assertEqual(len(PERSISTENCE),3)

    def test_identical_original_chunk_seeds_produce_identical_biomes_and_material(self):
        settings=make_editor_document("procedural_world")["settings"]
        for seed in (0,1,2,1984):
            scene=make_advanced_scene("procedural_world",seed=seed)
            self.assertEqual(validate_advanced_scene(scene),scene)
            layout=default_layout(settings,seed)
            self.assertEqual(normalize_layout(settings,layout),layout)
            self.assertEqual(_source_tile(settings,seed,-17,31),
                             _source_tile(settings,seed,-17,31))
            run=run_advanced_session("procedural_world",seed=seed,scene=scene)
            self.assertTrue(verify_advanced_session(run))
            self.assertFalse(run["native_hardware_verified"])

    def test_expedition_is_nonterminal_until_real_home_retirement(self):
        route=["east"]*3+["survey"]+["west"]*6+["north"]*2+[
            "survey","checkpoint"]+["south"]*2+["east"]*3
        for persistence in PERSISTENCE:
            settings={"persistence":persistence}
            result=run_advanced_session("procedural_world",settings,route)
            state=result["state"]
            self.assertEqual(state["surveyed"],[0,1])
            self.assertEqual(state["position"],[0,0])
            self.assertEqual(state["checkpoint_count"],1)
            self.assertTrue(state["expedition_complete"])
            self.assertFalse(state["finished"])
            self.assertTrue(verify_advanced_session(result,settings))
            ending=run_advanced_session("procedural_world",settings,route+["retire"])
            self.assertTrue(ending["state"]["finished"])
            self.assertTrue(ending["state"]["retired"])
            self.assertTrue(verify_advanced_session(ending,settings))

    def test_rebuild_world_forgets_unloaded_tile_edits(self):
        params={"persistence":"rebuild","active_chunks":1,"chunk_size":8}
        cfg=make_editor_document("procedural_world",params)["settings"]
        state=start(cfg,0)
        step(state,cfg,"build")
        self.assertEqual(_read(state,cfg,0,0)["structure"],"shelter")
        for _ in range(4):step(state,cfg,"sprint_east")
        self.assertEqual(state["chunk_evictions"],1)
        self.assertNotIn("0:0",state["edits"])
        for _ in range(4):step(state,cfg,"sprint_west")
        self.assertEqual(_read(state,cfg,0,0)["structure"],"none")
        self.assertEqual(state["persisted"],{})
        with self.assertRaises(ProceduralWorldActionError):
            step(state,cfg,"save")

    def test_save_deltas_persist_only_explicitly_committed_world_edits(self):
        params={"persistence":"save_deltas","active_chunks":1,"chunk_size":8}
        cfg=make_editor_document("procedural_world",params)["settings"]
        state=start(cfg,0)
        step(state,cfg,"build")
        step(state,cfg,"save")
        for _ in range(4):step(state,cfg,"sprint_east")
        for _ in range(4):step(state,cfg,"sprint_west")
        self.assertEqual(_read(state,cfg,0,0)["structure"],"shelter")
        self.assertEqual(state["save_count"],1)
        unsaved=start(cfg,0)
        step(unsaved,cfg,"build")
        for _ in range(4):step(unsaved,cfg,"sprint_east")
        for _ in range(4):step(unsaved,cfg,"sprint_west")
        self.assertEqual(_read(unsaved,cfg,0,0)["structure"],"none")

    def test_snapshot_commits_world_edit_on_chunk_eviction(self):
        params={"persistence":"snapshot","active_chunks":1,"chunk_size":8}
        cfg=make_editor_document("procedural_world",params)["settings"]
        state=start(cfg,0)
        step(state,cfg,"build")
        for _ in range(4):step(state,cfg,"sprint_east")
        self.assertEqual(state["persisted"]["0:0"]["structure"],"shelter")
        for _ in range(4):step(state,cfg,"sprint_west")
        self.assertEqual(_read(state,cfg,0,0)["structure"],"shelter")

    def test_physical_resources_and_bounded_edit_tracking(self):
        settings={"starting_wood":3,"starting_stone":2,
                  "max_edited_tiles":1}
        cfg=make_editor_document("procedural_world",settings)["settings"]
        state=start(cfg,0)
        step(state,cfg,"build")
        self.assertEqual(state["inventory"]["wood"],0)
        self.assertEqual(state["inventory"]["stone"],0)
        with self.assertRaises(ProceduralWorldActionError):
            step(state,cfg,"build")
        step(state,cfg,"east")
        with self.assertRaises(ProceduralWorldActionError):
            step(state,cfg,"build")
        self.assertEqual(state["structures_built"],1)

    def test_forged_world_seed_and_status_are_rejected(self):
        settings={"seed":43921}
        scene=make_advanced_scene("procedural_world",settings,seed=2)
        for tamper in (
            lambda s:s["layout"].update(world_seed=0),
            lambda s:s["layout"].update(story_terminal=True),
            lambda s:s["layout"]["landmarks"][0].update(id=1),
            lambda s:s["layout"].update(origin=[2,0]),
            lambda s:s.update(digest="f"*64),
        ):
            bad=deepcopy(scene);tamper(bad)
            with self.assertRaises(SceneError):
                validate_advanced_scene(bad,settings)
        proof=run_advanced_session("procedural_world",settings,["east"],seed=2)
        forged=deepcopy(proof)
        forged["state"]["inventory"]["ore"]=99999
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged,settings)

    def test_assembled_game_carries_real_generated_world_scene(self):
        spec=make_editor_document("procedural_world")
        scene=make_advanced_scene("procedural_world")
        build=compile_system_assembly("original_seeded_world",[spec],
                                      authorized=True,scenes=[scene])
        self.assertEqual(build["authored_scene_count"],1)
        self.assertEqual(build["advanced_runtime_evidence"][0]["editor"],
                         "procedural_world")

    def test_illegal_world_sizes_and_fake_budgets_fail_closed(self):
        for config in (
            {"chunk_size":7},{"biomes":0},
            {"seed":True},{"persistence":"teleport_save"},
            {"world_radius_chunks":1,"chunk_size":8},
            {"shelter_wood":20,"starting_wood":0,"resource_density":1},
        ):
            with self.assertRaises(SystemEditorError):
                make_editor_document("procedural_world",config)


if __name__=="__main__":
    unittest.main()
