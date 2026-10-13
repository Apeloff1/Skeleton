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
        self.assertEqual(len(editor["fields"]),70)
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



    def test_real_npc_role_can_initiate_quest_only_if_other_resident_witnessed_it(self):
        cfg=self.rules(npc_perception=3,npc_act_interval=10)
        # These ticks do not move the player or fabricate a player action.
        game=run_advanced_session("quest_director",cfg,
              ["wait:4","wait:4","wait","wait"])
        self.assertTrue(verify_advanced_session(game,cfg))
        state=game["state"]
        self.assertEqual(state["player"],0)
        self.assertEqual(state["npc_events_generated"],1)
        self.assertEqual(state["npcs"][0]["cargo"],1)
        self.assertEqual(state["npcs"][0]["personal_supplies"],cfg.get("npc_supplies",3))
        self.assertLess(state["sites"][0]["stock"],cfg.get("site_stock",12))
        event=state["events_log"][0]
        self.assertEqual(event["actor"],"npc:0")
        self.assertEqual(event["kind"],"discover")
        self.assertNotIn(0,event["direct_witnesses"])
        self.assertIn(1,event["direct_witnesses"])
        self.assertEqual(state["quests"][0]["origin_actor"],"npc:0")
        self.assertEqual(state["npcs"][1]["memories"][0]["source"],"eyewitness")
        self.assertEqual(state["reputation"],0)
        self.assertEqual(state["supplies"],cfg.get("starting_supplies",8))
        self.assertEqual(state["next_event"],1)
        # A self-originating NPC event does not create a self-witness.
        unwitnessed=self.rules(npc_perception=1,npc_act_interval=10)
        game=run_advanced_session("quest_director",unwitnessed,
              ["wait:4","wait:4","wait","wait"])
        self.assertEqual(game["state"]["npc_events_generated"],1)
        self.assertEqual(game["state"]["events_log"][0]["direct_witnesses"],[])
        self.assertEqual(game["state"]["quests"],[])

    def test_autonomous_npc_actions_consume_real_energy_and_finite_material_stock(self):
        cfg=self.rules(npc_count=1,npc_autonomy=True,
            npc_act_interval=1,npc_action_budget=20,
            site_stock=2,rumor_enabled=False)
        state=start(make_editor_document("quest_director",cfg)["settings"],0)
        for _ in range(6):step(state,make_editor_document("quest_director",cfg)["settings"],"wait")
        self.assertEqual(state["sites"][0]["stock"],0)
        self.assertEqual(state["npcs"][0]["cargo"],2)
        self.assertEqual(state["npc_events_generated"],2)
        self.assertEqual(state["npcs"][0]["energy"],3)
        self.assertEqual(state["reputation"],0)
        disabled=self.rules(npc_autonomy=False,npc_act_interval=1)
        quiet=run_advanced_session("quest_director",disabled,
              ["wait:4","wait:4"])
        self.assertEqual(quiet["state"]["events_log"],[])
        self.assertEqual(quiet["state"]["npc_events_generated"],0)

    def test_quest_director_event_rule_parameter_changes_actual_resolution_payment(self):
        common=self.rules(event_rules=100,rule_bonus_modulus=7,
                          ending_policy="persistent")
        itinerary=["south","east","help:0","speak:0",
                   "choose:0:support","help:0","resolve:0"]
        # Nonzero original seed gives a meaningful rule-id difference
        # while preserving the same source actions and real eyewitness path.
        sample=run_advanced_session("quest_director",common,itinerary,seed=4)
        one=run_advanced_session("quest_director",
                  {**common,"event_rules":1},itinerary,seed=4)
        self.assertTrue(verify_advanced_session(sample,common))
        self.assertTrue(verify_advanced_session(one,{**common,"event_rules":1}))
        self.assertEqual(one["state"]["quests"][0]["rule_id"],0)
        self.assertGreater(sample["state"]["quests"][0]["rule_id"],0)
        self.assertNotEqual(sample["state"]["gold"],one["state"]["gold"])


    def test_suspicion_risk_and_authored_climate_change_real_witness_reliability(self):
        # An adversarial eyewitness can be physically present but too
        # suspicious to offer trustworthy, first-hand testimony.
        risk=self.rules(starting_trust=5,testimony_trust_floor=1,
                        harm_suspicion=10,harm_trust_loss=0,
                        testimony_suspicion_tolerance=0)
        exposed=run_advanced_session("quest_director",risk,
                                    ["south","east","harm:0"])
        self.assertEqual(exposed["state"]["quests"][0]["witnesses"],[0])
        self.assertEqual(exposed["state"]["npcs"][0]["suspicion"],10)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("quest_director",risk,
                                 ["south","east","harm:0","speak:0"])

        # The same real NPC is visible in open highland air and concealed
        # by original rainforest geometry at otherwise identical positions.
        rules=self.rules(npc_count=1,npc_perception=2,witness_radius=3)
        default=make_advanced_scene("quest_director",rules,seed=0)
        changes=deepcopy(default["layout"])
        changes["npcs"][0]["cell"]=17
        changes["climate"]="highland"
        clear=make_advanced_scene("quest_director",rules,layout=changes)
        open_world=run_advanced_session("quest_director",rules,
                             ["south","east","collect:0"],scene=clear)
        self.assertEqual(open_world["state"]["events_log"][0]["direct_witnesses"],[0])
        changes["climate"]="rainforest"
        rainforest=make_advanced_scene("quest_director",rules,layout=changes)
        hidden=run_advanced_session("quest_director",rules,
                             ["south","east","collect:0"],scene=rainforest)
        self.assertEqual(hidden["state"]["events_log"][0]["direct_witnesses"],[])
        self.assertNotEqual(open_world["scene_digest"],hidden["scene_digest"])

    def test_forged_hearsay_cannot_promote_to_direct_memory_and_npc_quest_evidence(self):
        settings=self.rules(npc_perception=1,rumor_radius=2)
        source=run_advanced_session("quest_director",settings,
                ["south","east","collect:0","wait"])
        self.assertTrue(verify_advanced_session(source,settings))
        fabricated=deepcopy(source)
        fabricated["state"]["npcs"][1]["memories"].append({
            "event_id":0,"site_id":0,"kind":"discover",
            "observed_tick":3,"source":"eyewitness"
        })
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(fabricated,settings)
        fabricated=deepcopy(source)
        fabricated["state"]["events_log"][0]["direct_witnesses"].append(1)
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(fabricated,settings)


    def test_opt_in_npc_mobility_walks_one_real_tile_and_pays_energy(self):
        cfg=self.rules(npc_count=1,npc_mobility=True,
                       npc_patrol_interval=1,npc_walk_budget=1,
                       npc_pursues_evidence=False,npc_autonomy=False,
                       npc_move_energy_cost=2,npc_energy=5,
                       rumor_enabled=False)
        scene=make_advanced_scene("quest_director",cfg)
        modified=deepcopy(scene["layout"])
        modified["npcs"][0]["cell"]=10
        authored=make_advanced_scene("quest_director",cfg,layout=modified)
        result=run_advanced_session("quest_director",cfg,["wait","wait"],
                                    scene=authored)
        s=result["state"];npc=s["npcs"][0]
        self.assertEqual(npc["home"],10)
        self.assertEqual(npc["cell"],9)
        self.assertEqual(npc["walks"],1)
        self.assertEqual(s["npc_walks"],1)
        self.assertEqual(npc["energy"],3)
        self.assertEqual(npc["memories"],[])
        self.assertEqual(s["forensic_edges"],[])
        self.assertTrue(verify_advanced_session(result,cfg))
        inactive=run_advanced_session("quest_director",
               {**cfg,"npc_mobility":False},["wait","wait"],
               scene=make_advanced_scene("quest_director",
                 {**cfg,"npc_mobility":False},layout=modified))
        self.assertEqual(inactive["state"]["npcs"][0]["cell"],10)
        self.assertEqual(inactive["state"]["npc_walks"],0)

    def test_post_event_npc_investigation_can_never_become_direct_witness(self):
        cfg=self.rules(npc_count=1,npc_mobility=True,
            npc_pursues_evidence=True,npc_lead_radius=12,
            npc_perception=1,npc_patrol_interval=1,npc_walk_budget=32,
            npc_energy=30,npc_act_interval=64,
            rumor_enabled=False,day_ticks=100,quest_ttl=256,
            memory_decay_ticks=0)
        default=make_advanced_scene("quest_director",cfg)
        layout=deepcopy(default["layout"])
        layout["npcs"][0]["cell"]=33
        original=make_advanced_scene("quest_director",cfg,layout=layout)
        actions=["south","east","collect:0"]+["wait:4"]*7
        report=run_advanced_session("quest_director",cfg,
                         actions,scene=original)
        state=report["state"]
        self.assertEqual(state["events_log"][0]["direct_witnesses"],[])
        self.assertTrue(state["forensic_edges"])
        self.assertEqual(state["forensic_edges"][0]["event_id"],0)
        self.assertEqual(state["forensic_edges"][0]["authority"],
                         "forensic_after_event_not_eyewitness")
        self.assertFalse(state["npcs"][0]["memories"])
        self.assertFalse(state["quests"])
        self.assertGreater(state["npcs"][0]["walks"],0)
        self.assertTrue(verify_advanced_session(report,cfg))
        forged=deepcopy(report)
        forged["state"]["events_log"][0]["direct_witnesses"].append(0)
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged,cfg)
        forged=deepcopy(report)
        forged["state"]["forensic_edges"][0]["authority"]="eyewitness"
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged,cfg)

    def test_autonomous_event_receipt_carries_npc_actor_not_fake_player_causation(self):
        cfg=self.rules(npc_act_interval=1,npc_count=1,
                       npc_autonomy=True,npc_mobility=False)
        result=run_advanced_session("quest_director",cfg,["wait"])
        entry=result["state"]["events_log"][0]
        self.assertEqual(entry["actor"],"npc:0")
        self.assertEqual(entry["original_source"],
                         "physical_npc_world_action")
        self.assertEqual(result["state"]["reputation"],0)
        self.assertTrue(verify_advanced_session(result,cfg))

    def test_studio_original_witness_map_and_provenance_preserving_painter(self):
        from skeleton.ai.game_builder.game_workspace_ui import (
            render_workspace_html,SCRIPT,
        )
        page=render_workspace_html("A"*32).decode("utf-8")
        for token in ("quest-director-command","quest-director-context",
                      "quest-director-evidence","paintQuestDirectorCell",
                      "selectedQuestSite","selectedQuestNPC",
                      "advancedAvailableActions","site_move","npc_move",
                      "site_integrity_up","day_phase_next",
                      "Signed 7×7 witnessed quest",
                      "Original witnessed world changed.",
                      "testimonies","rumor_edges","original player action"):
            self.assertIn(token.lower(),page.lower())
        self.assertIn("physical witnessed-world action",SCRIPT)
        self.assertIn("Direct events",SCRIPT)
        self.assertIn("hearsay",SCRIPT)
        cfg=self.rules()
        scene=make_advanced_scene("quest_director",cfg,seed=4)
        changed=deepcopy(scene)
        changed["layout"]["climate"]="steppe"
        if changed["layout"]["climate"]==scene["layout"]["climate"]:
            changed["layout"]["climate"]="highland"
        with self.assertRaises(SceneError):
            validate_advanced_scene(changed,cfg)
        signed=make_advanced_scene("quest_director",cfg,seed=4,
                                   layout=changed["layout"])
        self.assertNotEqual(signed["digest"],scene["digest"])
        self.assertTrue(verify_advanced_session(
            run_advanced_session("quest_director",cfg,scene=signed,seed=4),cfg))

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
