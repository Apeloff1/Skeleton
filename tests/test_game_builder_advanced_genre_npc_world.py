"""Real original farming, ship cargo and aviation achievements affect NPC worlds."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_genre_npc_event_bridge import (
    SCHEMA,CrossGenreWorldError,
    run_cross_genre_world,verify_cross_genre_world,
)


class TrueGenreEventToNPCWorldTests(unittest.TestCase):
    @staticmethod
    def rules():
        return {"witnesses_required":1,"night_sight_penalty":0,
                "npc_perception":3,"witness_radius":3,"memory_decay_ticks":0,
                "event_rules":4,"quest_ttl":80,
                "npc_autonomy":False,"npc_mobility":False}

    @classmethod
    def world(cls):
        opts=cls.rules()
        return make_advanced_scene("quest_director",opts,seed=0),opts

    @staticmethod
    def farm():
        cfg={"crop_types":3,"field_tiles":4,"growth_days":2}
        scene=make_advanced_scene("farming",cfg,seed=0,layout={
            "plots":[{"id":i,"soil":5,"moisture":5} for i in range(4)],
            "market_multiplier":2,"starting_weather":"rain",
        })
        source=run_advanced_session("farming",cfg,
                ["plant:0","advance","harvest:0"],seed=0,scene=scene)
        return source,cfg

    @staticmethod
    def flight():
        opts=dict(flight_model="arcade",wind_strength=0,headwind=0,
                  fuel_capacity=500,stall_speed=10,route_length=40,
                  runway_length=12,launch_altitude=10,waypoint_floor=1,
                  waypoint_ceiling=30,landing_altitude=15,landing_speed=130,
                  terrain_height=0,drag=10,mass=20)
        scene=make_advanced_scene("flight",opts,seed=0)
        actions=[]
        for _ in range(35):
            state=run_advanced_session("flight",opts,actions,seed=0,scene=scene)["state"]
            if state["x"]>=state["runway_start"] and state["gear"]:
                actions.append("land");break
            actions.append("gear_down" if state["x"]>=state["runway_start"]-5
                           and not state["gear"] else "coast")
        source=run_advanced_session("flight",opts,actions,seed=0,scene=scene)
        assert source["state"]["landed"]
        return source,opts

    @staticmethod
    def sailing():
        opts={"wind_speed":30,"sail_area":100,"dynamic_currents":False,
              "route_length":40,"harbor_length":12,"max_speed":9,
              "safe_dock_speed":5,"launch_speed":3,"sea_state":0,
              "draft":1}
        scene=make_advanced_scene("sailing",opts,seed=0)
        actions=[]
        for _ in range(55):
            state=run_advanced_session("sailing",opts,actions,seed=0,scene=scene)["state"]
            if state["x"]>=state["harbor_start"] and state["anchor"]:
                actions.append("dock");break
            if state["x"]>=state["harbor_start"] and not state["anchor"]:
                actions.append("drop_anchor")
            elif state["x"]>=state["harbor_start"]-6 and state["sails"]:
                actions.append("lower")
            else:
                actions.append("coast")
        source=run_advanced_session("sailing",opts,actions,seed=0,scene=scene)
        assert source["state"]["cargo_delivered"]>0
        return source,opts

    @staticmethod
    def bind(source,site=0):
        name=source["editor"]
        kind={"farming":"mature_crop_harvested",
              "sailing":"original_cargo_delivered",
              "flight":"runway_landing_confirmed"}[name]
        index=next(i for i,frame in enumerate(source["trace"])
                   if kind in frame["events"])
        return {"trace_index":index,"site_id":site}

    def test_farming_harvest_creates_real_direct_npc_quest_not_fake_stock(self):
        source,cfg=self.farm()
        world,opts=self.world()
        original=deepcopy(source)
        result=run_cross_genre_world(source,world,[self.bind(source)],cfg,opts)
        self.assertEqual(source,original)
        self.assertEqual(result["schema"],SCHEMA)
        event=result["earned_events"][0]
        self.assertEqual(event["source_event"],"mature_crop_harvested")
        self.assertEqual(event["world_kind"],"discover")
        self.assertEqual(event["world_event"]["actor"],"external:genre")
        self.assertEqual(event["world_event"]["original_source"],
                         "signed_external_genre_gameplay_event")
        self.assertTrue(event["direct_witnesses"])
        self.assertTrue(event["original_quests"])
        self.assertEqual(event["real_stock"],0)
        self.assertEqual(result["world_state"]["reputation"],0)
        self.assertTrue(verify_cross_genre_world(result,source,world,cfg,opts))

    def test_earned_maritime_cargo_delivers_real_bounded_world_stock(self):
        source,cfg=self.sailing()
        world,opts=self.world()
        world_layout=deepcopy(world["layout"])
        world_layout["sites"][0]["stock"]=0
        world=make_advanced_scene("quest_director",opts,seed=0,layout=world_layout)
        result=run_cross_genre_world(source,world,[self.bind(source)],cfg,opts)
        event=result["earned_events"][0]
        self.assertEqual(event["source_event"],"original_cargo_delivered")
        self.assertEqual(event["real_stock"],1)
        self.assertEqual(result["world_state"]["sites"][0]["stock"],1)
        self.assertEqual(event["world_event"]["actor"],"external:genre")
        self.assertTrue(verify_cross_genre_world(result,source,world,cfg,opts))

    def test_safely_landed_aircraft_generates_real_corroborable_world_discovery(self):
        source,cfg=self.flight()
        world,opts=self.world()
        result=run_cross_genre_world(source,world,[self.bind(source)],cfg,opts)
        self.assertEqual(result["earned_events"][0]["source_event"],
                         "runway_landing_confirmed")
        self.assertEqual(result["earned_events"][0]["world_kind"],"discover")
        self.assertGreater(len(result["earned_events"][0]["direct_witnesses"]),0)
        self.assertFalse(result["source_game_files_changed"])
        self.assertTrue(verify_cross_genre_world(result,source,world,cfg,opts))

    def test_unearned_harvest_and_refused_landing_cannot_mint_npc_quests(self):
        world,opts=self.world()
        farm_opts={"crop_types":3,"field_tiles":4}
        farming=run_advanced_session(
            "farming",farm_opts,["plant:0"],seed=0,
            scene=make_advanced_scene("farming",farm_opts,seed=0))
        with self.assertRaises(CrossGenreWorldError):
            run_cross_genre_world(farming,world,[{"trace_index":0,"site_id":0}],
                                  farm_opts,opts)
        flight=run_advanced_session(
            "flight",actions=("land",),seed=0,
            scene=make_advanced_scene("flight",seed=0))
        with self.assertRaises(CrossGenreWorldError):
            run_cross_genre_world(flight,world,[{"trace_index":0,"site_id":0}])
        self.assertTrue(verify_advanced_session(flight))

    def test_world_followups_are_actually_simulated_without_player_reward_mint(self):
        source,cfg=self.farm()
        world,opts=self.world()
        proof=run_cross_genre_world(source,world,[self.bind(source)],cfg,opts,
                                    world_actions=("wait","inspect"))
        self.assertEqual(proof["world_state"]["turn"],3)
        self.assertEqual(proof["world_state"]["events_log"][0]["actor"],
                         "external:genre")
        self.assertEqual(len(proof["followup_timeline"]),2)
        self.assertTrue(verify_cross_genre_world(proof,source,world,cfg,opts))

    def test_event_action_site_and_duplicate_index_forgeries_rejected(self):
        source,cfg=self.farm()
        world,opts=self.world()
        event=self.bind(source)
        for bindings in (
            [event,event],
            [{"trace_index":True,"site_id":0}],
            [{"trace_index":-1,"site_id":0}],
            [{"trace_index":0,"site_id":4}],
            [{"trace_index":0}],
        ):
            with self.subTest(bindings=bindings),self.assertRaises(CrossGenreWorldError):
                run_cross_genre_world(source,world,bindings,cfg,opts)

    def test_original_gameplay_state_and_npc_testimony_mutation_denied(self):
        source,cfg=self.farm()
        world,opts=self.world()
        correct=run_cross_genre_world(source,world,[self.bind(source)],cfg,opts)
        variants=(
            lambda x:x["earned_events"][0]["world_event"].update(
                 direct_witnesses=[999]),
            lambda x:x["earned_events"][0].update(real_stock=99),
            lambda x:x["world_state"]["sites"][0].update(stock=99),
            lambda x:x["world_state"]["npcs"][0]["memories"].clear(),
            lambda x:x["earned_events"][0].update(head_hash="0"*64),
            lambda x:x.update(source_game_files_changed=True),
        )
        for alter in variants:
            fake=deepcopy(correct);alter(fake)
            with self.assertRaises(CrossGenreWorldError):
                verify_cross_genre_world(fake,source,world,cfg,opts)
        tampered=deepcopy(source)
        tampered["state"]["harvested"]=999
        with self.assertRaises(CrossGenreWorldError):
            run_cross_genre_world(tampered,world,[self.bind(source)],cfg,opts)

    def test_missing_source_and_unregistered_genre_rejected(self):
        source,cfg=self.farm()
        world,opts=self.world()
        for invalid in (None,[],{"editor":"made_up"}):
            with self.assertRaises(CrossGenreWorldError):
                run_cross_genre_world(invalid,world,[{"trace_index":0,"site_id":0}])
        wrong=deepcopy(source);wrong["scene"]=None
        with self.assertRaises(CrossGenreWorldError):
            run_cross_genre_world(wrong,world,[self.bind(source)],cfg,opts)


if __name__=="__main__":
    unittest.main()
