"""Real source-authorized if/and/or/not NPC world effects and replay custody."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_episodic_world import (
    run_episodic_physics_world,
)
from skeleton.ai.game_builder.advanced_npc_conditional_world import (
    NPCConditionalError,MAX_RULES,MAX_NODES,
    run_npc_conditional_rules,verify_npc_conditional_rules,
)


class OriginalNPCConditionalTests(unittest.TestCase):
    @staticmethod
    def game():
        cfg={
            "witnesses_required":1,"night_sight_penalty":0,
            "npc_perception":3,"witness_radius":3,"memory_decay_ticks":0,
            "event_rules":4,"quest_ttl":80,
            "npc_autonomy":False,"npc_mobility":False,
        }
        world=make_advanced_scene("quest_director",cfg,seed=0)
        scene=make_advanced_scene("racing",seed=1)
        source=run_advanced_session("racing",seed=1,scene=scene)
        episodes=[{
            "source_session":source,"source_settings":None,
            "physics_actions":["push:east"]*8,
            "bindings":[{"source_id":scene["layout"]["track_obstacle"],"site_id":0}],
            "world_actions":[],
        }]
        return episodes,world,cfg

    @staticmethod
    def fact(name,op="gte",value=1):
        return {"fact":name,"op":op,"value":value}

    @classmethod
    def rule(cls,when=None,action="aid",qid=0,rid="aid0"):
        return {
            "id":rid,"quest_id":qid,
            "when":when if when is not None else
                     cls.fact("source_eyewitnesses"),
            "do":action,
        }

    def test_genuine_eyewitness_and_damage_predicates_apply_real_community_aid(self):
        episodes,scene,cfg=self.game()
        original=deepcopy(episodes)
        condition={"all":[
            self.fact("source_eyewitnesses"),
            {"any":[self.fact("site_integrity","lte",11),
                    self.fact("player_supplies","gte",100)]},
            {"not":self.fact("quest_support_chosen","eq",1)}
        ]}
        rule=self.rule(condition)
        result=run_npc_conditional_rules(
            episodes,scene,[rule],cfg,mode="commit",authorized=True)
        self.assertEqual(original,episodes)
        self.assertEqual(result["applied_effects"],1)
        self.assertEqual(result["rule_results"][0]["result"],
                         "original_gameplay_actions_applied")
        self.assertEqual(result["rule_results"][0]["route"]["outcome"],
                         "finite_original_community_aid_delivered")
        self.assertIn("help:0",result["episodes"][-1]["world_actions"])
        self.assertEqual(len(result["world_state"]["relief_deliveries"]),1)
        self.assertEqual(result["world_state"]["supplies"],
                         run_episodic_physics_world(episodes,scene,cfg)
                         ["world_state"]["supplies"]-1)
        self.assertTrue(verify_npc_conditional_rules(result,episodes,scene,cfg))

    def test_preview_is_read_only_and_does_not_mint_reputation(self):
        episodes,scene,cfg=self.game()
        start=run_episodic_physics_world(episodes,scene,cfg)
        proof=run_npc_conditional_rules(
            episodes,scene,[self.rule()],cfg)
        self.assertEqual(proof["mode"],"preview")
        self.assertEqual(proof["applied_effects"],0)
        self.assertEqual(proof["episodes"],episodes)
        self.assertEqual(proof["world_state"],start["world_state"])
        self.assertEqual(proof["rule_results"][0]["result"],
                         "eligible_source_actions_preview_only")
        self.assertTrue(verify_npc_conditional_rules(proof,episodes,scene,cfg))

    def test_false_condition_causes_no_phantom_world_action(self):
        episodes,scene,cfg=self.game()
        rule=self.rule(self.fact("site_integrity","gte",50))
        result=run_npc_conditional_rules(
            episodes,scene,[rule],cfg,mode="commit",authorized=True)
        self.assertEqual(result["applied_effects"],0)
        self.assertEqual(result["rule_results"][0]["result"],"condition_false")
        self.assertEqual(result["episodes"],episodes)
        self.assertEqual(result["world_state"]["relief_deliveries"],[])
        self.assertTrue(verify_npc_conditional_rules(result,episodes,scene,cfg))

    def test_real_testimony_rule_does_not_replace_rumor(self):
        episodes,scene,cfg=self.game()
        rule=self.rule(
            {"all":[self.fact("reported_rumors","gte",0),
                    self.fact("real_testimonies","eq",0)]},
            action="testimony",rid="interview")
        result=run_npc_conditional_rules(
            episodes,scene,[rule],cfg,mode="commit",authorized=True)
        self.assertEqual(result["applied_effects"],1)
        quest=result["world_state"]["quests"][0]
        self.assertGreaterEqual(len(quest["testimonies"]),1)
        self.assertNotIn(999,quest["testimonies"])
        self.assertIn("speak:0",result["episodes"][-1]["world_actions"])

    def test_unearned_quest_resolve_is_not_auto_approved(self):
        episodes,scene,cfg=self.game()
        result=run_npc_conditional_rules(
            episodes,scene,[self.rule(action="resolve")],
            cfg,mode="commit",authorized=True)
        self.assertEqual(result["applied_effects"],0)
        self.assertEqual(result["rule_results"][0]["result"],
                         "reviewed_route_cannot_earn_objective")
        self.assertEqual(result["world_state"]["quests_completed"],0)

    def test_two_source_rules_recheck_new_world_state_between_applied_actions(self):
        episodes,scene,cfg=self.game()
        rules=[
            self.rule(self.fact("player_supplies","gte",8),rid="first"),
            self.rule(self.fact("player_supplies","lte",7),rid="second"),
        ]
        result=run_npc_conditional_rules(
            episodes,scene,rules,cfg,mode="commit",authorized=True)
        self.assertEqual(result["applied_effects"],2)
        self.assertEqual(len(result["world_state"]["relief_deliveries"]),2)
        self.assertEqual(result["rule_results"][0]["verified_facts"]["player_supplies"],8)
        self.assertEqual(result["rule_results"][1]["verified_facts"]["player_supplies"],7)
        self.assertTrue(verify_npc_conditional_rules(result,episodes,scene,cfg))

    def test_commit_requires_explicit_local_authorization(self):
        episodes,scene,cfg=self.game()
        with self.assertRaises(PermissionError):
            run_npc_conditional_rules(
                episodes,scene,[self.rule()],cfg,mode="commit")
        with self.assertRaises(NPCConditionalError):
            run_npc_conditional_rules(episodes,scene,[self.rule()],cfg,mode="automatic")
        preview=run_npc_conditional_rules(episodes,scene,[self.rule()],cfg)
        self.assertFalse(preview["source_game_files_mutated"])
        self.assertFalse(preview["unearned_npc_rewards_granted"])
        self.assertFalse(preview["native_device_certified"])

    def test_type_budget_and_recursive_predicates_fail_closed(self):
        episodes,scene,cfg=self.game()
        cases=[
            [self.rule({"all":[]})],
            [self.rule({"any":[self.fact("world_tick")]*7})],
            [self.rule({"not":{"not":{"not":{"not":{"not":
              self.fact("world_tick")}}}}})],
            [self.rule({"fact":"gold","op":"gte","value":1})],
            [self.rule({"fact":"world_tick","op":"gt","value":1})],
            [self.rule({"fact":"world_tick","op":"gte","value":True})],
            [self.rule({"fact":"world_tick","op":"gte","value":5000})],
            [self.rule({"fact":["world_tick"],"op":"gte","value":1})],
            [self.rule({"fact":"world_tick","op":["eq"],"value":1})],
            [self.rule(rid="same"),self.rule(rid="same")],
            [self.rule(rid="A Space")],
            [self.rule(qid=True)],
            [self.rule(action="mint_rewards")],
        ]
        for rules in cases:
            with self.subTest(rules=rules),self.assertRaises(NPCConditionalError):
                run_npc_conditional_rules(episodes,scene,rules,cfg)
        self.assertEqual(MAX_RULES,12)
        self.assertEqual(MAX_NODES,16)

    def test_fake_rule_attestation_and_client_reward_replay_fail(self):
        episodes,scene,cfg=self.game()
        good=run_npc_conditional_rules(
            episodes,scene,[self.rule()],cfg,mode="commit",authorized=True)
        cases=(
            lambda x:x["rule_results"][0]["verified_facts"].update(
                     real_testimonies=10),
            lambda x:x["rule_results"][0]["route"].update(
                     outcome="unearned_win"),
            lambda x:x["rule_results"][0].update(head_hash="0"*64),
            lambda x:x["world_state"]["sites"][0].update(integrity=999),
            lambda x:x["episodes"][-1]["world_actions"].append("teleport"),
            lambda x:x.update(applied_effects=99),
            lambda x:x.update(unearned_npc_rewards_granted=True),
        )
        for tamper in cases:
            altered=deepcopy(good);tamper(altered)
            with self.assertRaises(NPCConditionalError):
                verify_npc_conditional_rules(altered,episodes,scene,cfg)

    def test_scene_or_source_session_cannot_be_swapped_between_rules(self):
        episodes,scene,cfg=self.game()
        good=run_npc_conditional_rules(
            episodes,scene,[self.rule()],cfg)
        wrong=make_advanced_scene("quest_director",cfg,seed=2)
        with self.assertRaises(NPCConditionalError):
            verify_npc_conditional_rules(good,episodes,wrong,cfg)
        changes=deepcopy(episodes)
        changes[0]["source_session"]["state"]["fuel"]=999
        with self.assertRaises(NPCConditionalError):
            run_npc_conditional_rules(changes,scene,[self.rule()],cfg)


if __name__=="__main__":
    unittest.main()
