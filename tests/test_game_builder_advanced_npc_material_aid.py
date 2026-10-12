"""Real resource-funded recovery quests after signed physical incidents."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_episodic_world import (
    EpisodicWorldError,run_episodic_physics_world,verify_episodic_physics_world,
)
from skeleton.ai.game_builder.advanced_npc_evidence_navigation import (
    navigate_verified_investigation,verify_investigation_navigation,
)
from skeleton.ai.game_builder.advanced_quest_director_runtime import (
    QuestDirectorError,start as start_quest,step as quest_step,
)
from skeleton.ai.game_builder.system_editors import make_editor_document


class OriginalMaterialRecoveryTests(unittest.TestCase):
    @staticmethod
    def config(**overrides):
        return {
            "witnesses_required":1,"night_sight_penalty":0,
            "npc_perception":3,"witness_radius":3,"memory_decay_ticks":0,
            "event_rules":4,"quest_ttl":80,
            "npc_autonomy":False,"npc_mobility":False,
            **overrides
        }

    @classmethod
    def campaign(cls,config=None,actions=()):
        rules=config if config is not None else cls.config()
        scene=make_advanced_scene("racing",seed=1)
        origin=run_advanced_session("racing",seed=1,scene=scene)
        world=make_advanced_scene("quest_director",rules,seed=0)
        episode={
            "source_session":origin,"source_settings":None,
            "physics_actions":["push:east"]*8,
            "bindings":[{"source_id":scene["layout"]["track_obstacle"],
                         "site_id":0}],
            "world_actions":list(actions),
        }
        return run_episodic_physics_world([episode],world,rules),[episode],world,rules

    def test_default_consequence_depth_has_real_non_destructive_completion(self):
        actions=("east","east","speak:0","choose:0:support","west","repair:0",
                 "help:0","help:0","help:0","help:0","resolve:0")
        proof,episodes,scene,rules=self.campaign(actions=actions)
        q=next(q for q in proof["world_state"]["quests"] if q["id"]==0)
        self.assertEqual(q["status"],"resolved")
        self.assertEqual(q["ending"],"restored")
        self.assertEqual(q["material_actions"],5)
        self.assertEqual(proof["world_state"]["quests_completed"],1)
        self.assertEqual(proof["world_state"]["quests_exploited"],0)
        self.assertEqual(len(proof["world_state"]["relief_deliveries"]),4)
        self.assertTrue(all(delivery["site_id"]==0 for delivery in
                            proof["world_state"]["relief_deliveries"]))
        self.assertTrue(verify_episodic_physics_world(proof,episodes,scene,rules))

    def test_delivering_supplies_is_finite_and_cannot_be_client_minted(self):
        proof,episodes,scene,rules=self.campaign(actions=(
            "east","help:0","help:0"))
        supplies=make_editor_document("quest_director",rules)["settings"]["starting_supplies"]
        self.assertEqual(proof["world_state"]["supplies"],supplies-2)
        self.assertEqual(len(proof["world_state"]["relief_deliveries"]),2)
        self.assertEqual(sum(x["finite_supplies_distributed"] for x in
                             proof["world_state"]["relief_deliveries"]),2)
        for mutate in (
            lambda p:p["world_state"]["relief_deliveries"][0].update(
                finite_supplies_distributed=999),
            lambda p:p["world_state"]["relief_deliveries"].clear(),
            lambda p:p["episodes"][0].update(quests_completed=999),
        ):
            altered=deepcopy(proof)
            mutate(altered)
            with self.assertRaises(EpisodicWorldError):
                verify_episodic_physics_world(altered,episodes,scene,rules)

    def test_zero_cost_no_effect_help_cannot_mint_quest_rewards(self):
        cfg=make_editor_document("quest_director",self.config(
            help_supplies=0))["settings"]
        world=start_quest(cfg,seed=0)
        quest_step(world,cfg,"east")
        original=deepcopy(world)
        with self.assertRaises(QuestDirectorError):
            quest_step(world,cfg,"help:0")
        self.assertEqual(world,original)

    def test_real_aid_navigation_executes_actual_original_world_rules(self):
        proof,episodes,world,rules=self.campaign()
        planned=navigate_verified_investigation(
            proof,episodes,world,rules,quest_id=0,objective="aid")
        self.assertEqual(planned["outcome"],"finite_original_community_aid_delivered")
        self.assertIn("help:0",planned["planned_and_simulated_actions"])
        self.assertTrue(planned["end_world_state"]["relief_deliveries"])
        self.assertLess(planned["end_world_state"]["supplies"],
                        proof["world_state"]["supplies"])
        self.assertTrue(verify_investigation_navigation(
            planned,proof,episodes,world,rules))

    def test_no_unearned_supply_from_zero_stock_for_navigation(self):
        rules=self.config(starting_supplies=0)
        proof,episodes,world,rules=self.campaign(rules)
        report=navigate_verified_investigation(
            proof,episodes,world,rules,quest_id=0,objective="aid")
        self.assertEqual(report["outcome"],
                         "real_material_relief_requires_finite_source_resources")
        self.assertEqual(report["planned_and_simulated_actions"],[])
        self.assertEqual(report["end_world_state"]["relief_deliveries"],[])

    def test_relief_quest_not_disguised_as_unearned_player_damage(self):
        original,_,_,_=self.campaign()
        outcome,episodes,scene,rules=self.campaign(actions=("east","help:0"))
        self.assertGreater(outcome["world_state"]["reputation"],0)
        self.assertEqual(outcome["world_state"]["events_log"][0]["actor"],
                         "external:physics")
        later=outcome["world_state"]["events_log"][-1]
        self.assertEqual(later["actor"],"player")
        self.assertEqual(later["kind"],"help")
        self.assertEqual(outcome["world_state"]["relief_deliveries"][0]
                         ["original_source"],"real_player_world_aid")
        self.assertEqual(original["world_state"]["reputation"],0)
        self.assertTrue(verify_episodic_physics_world(outcome,episodes,scene,rules))


if __name__=="__main__":
    unittest.main()
