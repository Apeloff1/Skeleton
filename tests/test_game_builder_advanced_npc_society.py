"""Living NPC Society: spatial witnessed events, adaptive LOD and civic proof."""
from __future__ import annotations
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_npc_society_runtime import (
    ACTIONS,PROFESSIONS,SocietyActionError,default_layout,normalize_layout,
    start,step,
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


class OriginalSocietyTests(unittest.TestCase):
    @staticmethod
    def quiet(**overrides):
        settings={"simulation_lod":"background","coarse_period":16}
        settings.update(overrides)
        return settings

    def test_society_reference_has_real_bounded_residents_and_actions(self):
        self.assertIn("npc_society",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["npc_society"]))
        spec=next(e for e in catalog() if e["id"]=="npc_society")
        self.assertEqual(spec["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(spec["progression_floor"],"advanced")
        self.assertGreaterEqual(len(spec["fields"]),30)
        self.assertEqual(len(PROFESSIONS),6)
        big=run_advanced_session("npc_society",{
            "population":100000,"active_npcs":10000
        },["wait"]*2)
        self.assertEqual(big["state"]["population"],100000)
        self.assertLessEqual(big["state"]["embodied"],32)
        self.assertGreater(big["state"]["background_population"],99900)
        self.assertTrue(verify_advanced_session(big,{
            "population":100000,"active_npcs":10000
        }))

    def test_each_source_seed_creates_exact_signed_witnesses(self):
        for seed in (0,1,2,31):
            rules=make_editor_document("npc_society")["settings"]
            level=default_layout(rules,seed)
            self.assertEqual(normalize_layout(rules,level),level)
            scene=make_advanced_scene("npc_society",seed=seed)
            self.assertEqual(validate_advanced_scene(scene),scene)
            proof=run_advanced_session("npc_society",seed=seed,scene=scene)
            self.assertTrue(verify_advanced_session(proof))
            self.assertFalse(proof["native_hardware_verified"])

    def test_independent_witnesses_are_required_for_civic_milestone(self):
        settings=self.quiet()
        actions=[
            "observe","focus:1","observe",
            "east","east","east","north","north","north",
            "mediate","checkpoint",
        ]
        result=run_advanced_session("npc_society",settings,actions)
        state=result["state"]
        self.assertTrue(state["incident_resolved"])
        self.assertTrue(state["community_checkpoint"])
        self.assertFalse(state["finished"])
        self.assertEqual(state["festival_count"],1)
        self.assertEqual(state["position"],[4,4])
        self.assertEqual(state["evidence"],
                         ["observed_resident_0","observed_resident_1"])
        self.assertTrue(any(m["kind"]=="civic_mediation" for m in state["memories"]))
        self.assertTrue(verify_advanced_session(result,settings))
        end=run_advanced_session(
            "npc_society",settings,
            actions+["west","west","west","south","south","south","retire"],
        )
        self.assertTrue(end["state"]["retired"])
        self.assertTrue(end["state"]["finished"])
        self.assertTrue(verify_advanced_session(end,settings))

    def test_background_adaptive_and_full_have_different_real_workloads(self):
        totals=[]
        for mode in ("full","adaptive","background"):
            config={"simulation_lod":mode,"coarse_period":8}
            record=run_advanced_session("npc_society",config,["wait"]*7)
            self.assertTrue(verify_advanced_session(record,config))
            totals.append(record["state"]["full_updates"])
        self.assertGreater(totals[0],totals[1])
        self.assertGreater(totals[1],totals[2])
        self.assertEqual(totals[2],0)

    def test_real_trade_preserves_both_money_and_goods_and_records_witness(self):
        settings=self.quiet()
        proof=run_advanced_session(
            "npc_society",settings,["east","focus:2","trade"],
        )
        state=proof["state"]
        self.assertEqual(state["gold"],47)
        self.assertEqual(state["materials"],29)
        self.assertEqual(state["food"],94)
        self.assertEqual(state["memories"][0]["proof"],"paid_goods_and_gold")
        self.assertTrue(verify_advanced_session(proof,settings))

    def test_memory_limit_does_not_invent_infinite_knowledge(self):
        settings=self.quiet(memory_records=1)
        proof=run_advanced_session("npc_society",settings,["talk"]*4)
        self.assertEqual(len(proof["state"]["memories"]),1)
        self.assertEqual(proof["state"]["trust"],4)
        self.assertTrue(verify_advanced_session(proof,settings))

    def test_spoofed_witness_and_replay_memory_cannot_promote(self):
        scene=make_advanced_scene("npc_society")
        for mutate in (
            lambda x:x["layout"]["witnesses"][0].update(id=2),
            lambda x:x["layout"]["witnesses"][1].update(work=[4,4]),
            lambda x:x["layout"].update(incident="admin_override"),
            lambda x:x["layout"].update(world_terminal=True),
            lambda x:x.update(digest="f"*64),
        ):
            invalid=deepcopy(scene);mutate(invalid)
            with self.assertRaises(SceneError):
                validate_advanced_scene(invalid)
        result=run_advanced_session("npc_society",actions=["talk"])
        forged=deepcopy(result)
        forged["state"]["evidence"]=["observed_resident_0","observed_resident_1"]
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("npc_society",actions=["mediate"])

    def test_resident_presence_and_finite_witness_memory_enforced(self):
        config=self.quiet(active_npcs=2)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("npc_society",config,["focus:7"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("npc_society",config,["retire"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("npc_society",config,["accuse"])

    def test_source_custody_survives_composite_game_assembly(self):
        settings=self.quiet()
        scene=make_advanced_scene("npc_society",settings)
        proof=compile_system_assembly(
            "original_society",[make_editor_document("npc_society",settings)],
            authorized=True,scenes=[scene],
        )
        self.assertEqual(proof["authored_scene_count"],1)
        self.assertEqual(proof["advanced_runtime_evidence"][0]["editor"],
                         "npc_society")

    def test_invalid_population_and_invented_resources_rejected(self):
        for values in (
            {"population":100,"active_npcs":101},
            {"initial_food":600,"food_capacity":100},
            {"initial_materials":300,"material_capacity":100},
            {"work_energy":30,"player_energy":10},
            {"simulation_lod":"superhuman"},
            {"memory_records":True},
        ):
            with self.assertRaises(SystemEditorError):
                make_editor_document("npc_society",values)


if __name__=="__main__":
    unittest.main()
