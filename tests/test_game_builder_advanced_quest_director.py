"""Twenty playable original families: causal NPC witnesses and branching worlds."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io,json,unittest

from skeleton.ai.game_builder.advanced_quest_director_runtime import (
    ACTIONS,CELLS,QuestDirectorError,default_layout,normalize_layout,
    start,step,
)
from skeleton.ai.game_builder.system_editors import (
    catalog,make_editor_document,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError,make_advanced_scene,validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES,ACTION_HELP,AdvancedRuntimeError,
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame,import_advanced_savegame,continue_advanced_savegame,
)
from skeleton.ai.game_builder.system_editor_assembly import compile_system_assembly


class LivingOriginalQuestTests(unittest.TestCase):
    @staticmethod
    def rules(**overrides):
        return {"consequence_depth":1,"quest_goal":1,"npc_perception":2,
                "memory_decay_ticks":0,"quest_ttl":80,
                "night_sight_penalty":0,**overrides}

    @staticmethod
    def witness_start():
        return ["south","east","collect:0","speak:0"]

    def test_twentieth_family_actual_53_control_source_bound_engine(self):
        self.assertIn("quest_director",ENGINES)
        self.assertEqual(set(ACTIONS),set(ACTION_HELP["quest_director"]))
        editor=next(e for e in catalog() if e["id"]=="quest_director")
        self.assertEqual(editor["runtime_maturity"],"advanced_reference_runtime")
        self.assertEqual(editor["progression_floor"],"advanced")
        self.assertEqual(len(editor["fields"]),53)
        self.assertEqual(len(ACTIONS),len(set(ACTIONS)))
        self.assertEqual(CELLS,49)

    def test_original_authored_sources_are_connected_finite_and_signed(self):
        for seed in (0,1,5,7,99):
            config=make_editor_document("quest_director")["settings"]
            source=default_layout(config,seed)
            self.assertEqual(normalize_layout(config,source),source)
            self.assertEqual(len(source["sites"]),4)
            self.assertEqual(len(source["npcs"]),4)
            scene=make_advanced_scene("quest_director",seed=seed)
            self.assertEqual(validate_advanced_scene(scene),scene)
            game=run_advanced_session("quest_director",seed=seed,scene=scene)
            self.assertEqual(game["state"]["player"],0)
            self.assertEqual(game["state"]["events_log"],[])
            self.assertFalse(game["native_hardware_verified"])
            self.assertTrue(verify_advanced_session(game))

    def test_real_local_eyewitness_initiates_quest_and_testimony_cannot_be_forged(self):
        rules=self.rules()
        game=run_advanced_session("quest_director",rules,self.witness_start())
        self.assertTrue(verify_advanced_session(game,rules))
        s=game["state"]
        self.assertEqual(s["player"],8)
        self.assertEqual(s["events_log"][0]["kind"],"discover")
        self.assertEqual(s["events_log"][0]["direct_witnesses"],[0])
        self.assertEqual(s["quests"][0]["trigger"],"discover")
        self.assertEqual(s["quests"][0]["testimonies"],[0])
        self.assertEqual(s["npcs"][0]["memories"][0]["source"],"eyewitness")
        self.assertEqual(s["sites"][0]["stock"],10)
        self.assertGreater(s["supplies"],rules.get("starting_supplies",8))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",rules,["choose:0:support"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",rules,["speak:0"])

    def test_corroborated_support_requires_real_second_site_action_and_source_presence(self):
        rules=self.rules(ending_policy="campaign",nonterminal_world=False)
        beginning=self.witness_start()
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",rules,
                      beginning+["choose:0:support","resolve:0"])
        finished=run_advanced_session("quest_director",rules,
                 beginning+["choose:0:support","help:0","resolve:0"])
        s=finished["state"]
        self.assertTrue(s["victory"])
        self.assertTrue(s["finished"])
        self.assertEqual(s["reason"],"actual_corrobated_witness_campaign_completed")
        self.assertEqual(s["quests_completed"],1)
        self.assertEqual(s["quests"][0]["ending"],"restored")
        self.assertGreater(s["gold"],rules.get("starting_gold",5))
        self.assertEqual(len(s["milestones"]),1)
        self.assertEqual(s["milestones"][0]["evidence"],[0])
        self.assertTrue(verify_advanced_session(finished,rules))
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",rules,
              beginning+["choose:0:support","help:0","resolve:0","inspect"])

    def test_nonterminal_postgame_keeps_player_movement_and_real_quests(self):
        rules=self.rules(ending_policy="persistent",nonterminal_world=True)
        run=self.witness_start()+["choose:0:support","help:0",
                                  "resolve:0","inspect","east"]
        result=run_advanced_session("quest_director",rules,run)
        self.assertTrue(result["state"]["victory"])
        self.assertFalse(result["state"]["finished"])
        self.assertFalse(result["terminal"])
        self.assertEqual(result["state"]["player"],9)
        self.assertTrue(verify_advanced_session(result,rules))

    def test_real_harm_and_exploit_alternative_has_material_cost_and_reputation(self):
        rules=self.rules(quest_goal=3)
        actions=["south","east","harm:0","speak:0",
                 "choose:0:exploit","harm:0","resolve:0"]
        game=run_advanced_session("quest_director",rules,actions)
        s=game["state"]
        self.assertTrue(verify_advanced_session(game,rules))
        self.assertEqual(s["quests_exploited"],1)
        self.assertEqual(s["quests"][0]["ending"],"exploited")
        self.assertEqual(s["quests"][0]["trigger"],"harm")
        self.assertLess(s["reputation"],0)
        self.assertGreater(s["npcs"][0]["suspicion"],0)
        self.assertLess(s["sites"][0]["integrity"],12)
        self.assertFalse(s["victory"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",rules,
                ["south","east","harm:0","speak:0","choose:0:support","harm:0","resolve:0"])

    def test_rumors_reach_neighbors_not_full_map_and_never_become_eyewitnesses(self):
        rules=self.rules(rumor_radius=2,rumor_interval=2,npc_perception=1)
        state=run_advanced_session("quest_director",rules,
                 ["south","east","collect:0","wait"]).get("state")
        original=state["events_log"][0]
        self.assertEqual(original["direct_witnesses"],[0])
        self.assertIn(1,original["rumored_to"])
        self.assertNotIn(1,original["direct_witnesses"])
        recipient=state["npcs"][1]
        self.assertFalse(recipient["memories"])
        self.assertEqual(recipient["heard"][0]["source"],"rumor")
        self.assertTrue(all(edge["authority"]=="rumor_only_not_eye_witness"
                            for edge in state["rumor_edges"]))
        self.assertFalse(state["npcs"][2]["heard"])
        # Player may travel to real recipient, but cannot substitute hearsay
        # for authenticated direct testimony.
        result=run_advanced_session("quest_director",rules,
                 ["south","east","collect:0","wait","south","east","speak:1"])
        q=result["state"]["quests"][0]
        self.assertEqual(q["testimonies"],[])
        self.assertEqual(q["heard_from"],[1])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",rules,
                 ["south","east","collect:0","wait","south","east",
                  "speak:1","choose:0:support"])

    def test_wall_blocked_sight_cannot_mint_unwitnessed_quests(self):
        rules=self.rules(npc_count=1,witness_radius=2)
        signed=make_advanced_scene("quest_director",rules)
        authored=deepcopy(signed["layout"])
        authored["obstacles"]=[9,18,37]
        authored["npcs"][0]["cell"]=10
        scene=make_advanced_scene("quest_director",rules,layout=authored)
        game=run_advanced_session("quest_director",rules,
              ["south","east","collect:0"],scene=scene)
        self.assertEqual(game["state"]["events_log"][0]["direct_witnesses"],[])
        self.assertEqual(game["state"]["quests"],[])
        self.assertTrue(verify_advanced_session(game,rules))

    def test_night_perception_and_low_trust_block_false_testimony(self):
        rules=self.rules(npc_perception=1,day_ticks=4,
                    night_fraction_percent=50,night_sight_penalty=1)
        night=run_advanced_session("quest_director",rules,
                   ["south","east","collect:0"])
        self.assertEqual(night["state"]["events_log"][0]["direct_witnesses"],[])
        self.assertEqual(night["state"]["quests"],[])
        low_trust=self.rules(starting_trust=1,testimony_trust_floor=2)
        report=run_advanced_session("quest_director",low_trust,
                         ["south","east","collect:0"])
        self.assertTrue(report["state"]["quests"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",low_trust,self.witness_start())

    def test_rigorous_signed_source_rejects_identity_spoof_stock_and_disconnected_world(self):
        rules=self.rules()
        config=make_editor_document("quest_director",rules)["settings"]
        signed=make_advanced_scene("quest_director",rules,seed=6)
        for edit in (
            lambda l:l["sites"][0].update(stock=999999),
            lambda l:l["sites"][0].update(id=3),
            lambda l:l["sites"][0].update(kind="protected_movie_location"),
            lambda l:l["sites"][0].update(cell=l["npcs"][0]["cell"]),
            lambda l:l["npcs"][0].update(trust=999),
            lambda l:l["npcs"][0].update(role="licensed_character"),
            lambda l:l["npcs"][0].update(script="execute"),
            lambda l:l["obstacles"].append(l["sites"][0]["cell"]),
            lambda l:l.update(player_spawn=l["sites"][1]["cell"]),
            lambda l:l.update(day_phase=10000),
            lambda l:l.update(climate="imported_franchise"),
        ):
            forged=deepcopy(signed["layout"])
            edit(forged)
            with self.assertRaises(QuestDirectorError):
                normalize_layout(config,forged)
        edited=deepcopy(signed)
        edited["layout"]["climate"]="steppe"
        if signed["layout"]["climate"]=="steppe":
            edited["layout"]["climate"]="highland"
        with self.assertRaises(SceneError):
            validate_advanced_scene(edited,rules)
        rebuilt=make_advanced_scene("quest_director",rules,
                           seed=6,layout=edited["layout"])
        self.assertNotEqual(signed["digest"],rebuilt["digest"])
        self.assertEqual(validate_advanced_scene(rebuilt,rules),rebuilt)

    def test_unregistered_phantom_quests_rejected_even_when_player_has_supplies(self):
        rules=self.rules()
        for action in ("teleport:8","spawn_quest:0","witness:0","force_win",
                       "choose:12:support","resolve:13","speak:4"):
            with self.assertRaises(AdvancedRuntimeError):
                run_advanced_session("quest_director",rules,[action])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",rules,["help:0"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",rules,["east"]*129)
        sparse=self.rules(npc_count=1)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",sparse,["speak:3"])

    def test_savegame_and_hybrid_reference_proof_rebuild_full_original_witness_history(self):
        rules=self.rules()
        scene=make_advanced_scene("quest_director",rules,seed=5)
        session=run_advanced_session("quest_director",rules,
                  ["south","east","collect:0"],seed=5,scene=scene)
        self.assertTrue(verify_advanced_session(session,rules))
        save=export_advanced_savegame(session,rules)
        self.assertEqual(import_advanced_savegame(save)["session"],session)
        resumed=continue_advanced_savegame(save,["speak:0"])
        self.assertTrue(import_advanced_savegame(resumed)["verified"])
        for alter in (
            lambda s:s["npcs"][0]["memories"][0].update(source="eyewitness_fake"),
            lambda s:s["events_log"][0].update(direct_witnesses=[0,1,2,3]),
            lambda s:s["quests"][0].update(testimonies=[0,1,2,3]),
            lambda s:s.update(gold=999999),
            lambda s:s.update(victory=True),
            lambda s:s["sites"][0].update(stock=10000),
        ):
            modified=deepcopy(session);alter(modified["state"])
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(modified,rules)
        assembled=compile_system_assembly("original_npc_causal_world",
                [make_editor_document("quest_director",rules)],
                authorized=True,scenes=[scene])
        self.assertEqual(assembled["authored_scene_count"],1)
        self.assertEqual(assembled["advanced_runtime_evidence"][0]["editor"],
                         "quest_director")
        self.assertFalse(assembled["ready_for_release"])
        from skeleton.ai.game_builder.system_editor_cli import main
        stdout=io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(main(["play","--editor","quest_director",
                                   "--seed","0"]),0)
        self.assertTrue(verify_advanced_session(json.loads(stdout.getvalue())))


if __name__=="__main__":
    unittest.main()
