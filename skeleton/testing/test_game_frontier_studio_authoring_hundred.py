"""Acceptance suite for 100 genuine Forge Studio production operations 151–250.

Distinct per-action test cases prove actual source mutation. This suite also
checks transactional replay, reachability, environmentally evaluated action
proposals, revision-codec persistence and typed source boundaries.
"""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioProject, StudioPlacement, StudioQuest, StudioQuestStage, StudioError,
    MapLayer, compile_studio_native_quest_graph,
)
from skeleton.forge.game_frontier_rpg_events import (
    EnvironmentalTrigger, RPGEventAction, RPGEventPage, evaluate_environment_events,
)
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, execute_authoring, apply_authoring_batch, project_digest,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.forge.game_frontier_studio_topology_edit import TERRAIN_TOPOLOGY_ACTIONS
from skeleton.forge.game_frontier_studio_actor_layout_edit import ACTOR_LAYOUT_ACTIONS
from skeleton.forge.game_frontier_studio_story_production_edit import STORY_PRODUCTION_ACTIONS
from skeleton.forge.game_frontier_studio_environment_composer import (
    SENSOR_ACTIONS, PAGE_COMPOSER_ACTIONS, ENVIRONMENT_COMPOSER_ACTIONS,
)
from skeleton.testing.test_game_frontier_studio_authoring import project as initial_project


def project():
    base=initial_project()
    layer=MapLayer("topology",16,16,("floor","wall","water"),
                   tuple(x%3 for y in range(16) for x in range(16)))
    # In addition to the native fixture's first two actors, keep one at an
    # unequal position for actual group-spacing and facing transformations.
    actors=tuple(replace(p,facing_deg=(15 if i==0 else 110))
                 for i,p in enumerate(base.placements))+(StudioPlacement("tree",11,8,4,225),)
    q=StudioQuest("story","Story","first",(
        StudioQuestStage("first","Start",("middle","side","detour")),
        StudioQuestStage("middle","Explore",("endingA","endingB")),
        StudioQuestStage("side","Investigate"),
        StudioQuestStage("detour","Take the trail",("endingB",)),
        StudioQuestStage("endingA","Return home"),
        StudioQuestStage("endingB","Go beyond"),
    ))
    page=RPGEventPage("weather_rise",5,(
        EnvironmentalTrigger("altitude_m","above",20),
        EnvironmentalTrigger("rain_mm_h","above",3),
    ),(
        RPGEventAction("set_flag","world","rain_observed","true"),
        RPGEventAction("start_quest","quest","story","story"),
    ))
    return replace(base, layers=(layer,)+base.layers,
                   placements=actors, native_quests=(q,),
                   environmental_pages=(page,))


TOPOLOGY={name:{
    "layer":"topology","x":0,"y":0,"width":12,"height":12,
    "floor":0,"wall":1,"seed":42,
} for name in TERRAIN_TOPOLOGY_ACTIONS}
for name in ("terrain_bezier_road","terrain_spline_river"):
    TOPOLOGY[name]["control_points"]=[[0,0],[6,9],[11,11]]
TOPOLOGY["terrain_archipelago_bridges"]["seed"]=42
TOPOLOGY["terrain_edge_falloff"]["margin"]=2
TOPOLOGY["terrain_ruin_foundations"]["buildings"]=6
TOPOLOGY["terrain_random_walker"]["steps"]=100

ACTORS={name:{"indices":[0,1,2]} for name in ACTOR_LAYOUT_ACTIONS}
ACTORS["actors_snap_grid"]["step"]=2
ACTORS["actors_snap_ground"]["ground_z"]=5
ACTORS["actors_quantize_facing"]["degrees"]=45
ACTORS["actors_face_point"].update({"target_x":12,"target_y":12})
ACTORS["actors_face_actor"].update({"indices":[0],"target_index":2})
ACTORS["actors_align_x"]["value"]=5
ACTORS["actors_align_y"]["value"]=5
ACTORS["actors_radial_expand"]["distance"]=2
ACTORS["actors_radial_contract"]["distance"]=1
ACTORS["actors_scale_cloud"]["factor"]=1.5
ACTORS["actors_shift_altitude"]["dz"]=2
ACTORS["actors_seeded_jitter"].update({"seed":42,"amplitude":2})
ACTORS["actors_separate_overlap"]["minimum_distance"]=20
ACTORS["actors_snap_terrain"]["layer"]="topology"
ACTORS["actors_clamp_bounds"].update({"min_x":2,"max_x":8,"min_y":2,"max_y":8})
ACTORS["actors_swap_poses"]["indices"]=[0,1]
ACTORS["actors_copy_facing"].update({"indices":[0,1],"source_index":2})
ACTORS["actors_center_group"].update({"x":12,"y":12})
ACTORS["actors_wave_offsets"].update({"amplitude":2,"period":3})
ACTORS["actors_staircase"]["step"]=2
ACTORS["actors_terrain_walk"]["layer"]="topology"
ACTORS["actors_depth_rank"].update({"base_z":4,"step_z":2})
ACTORS["actors_random_facing"]["seed"]=42
ACTORS["actors_clone_selected"].update({"dx":3,"dy":2,"dz":0})

STORY={
    "quest_add_prologue":{"quest_id":"story","new_stage_id":"prelude","objective":"Before the first event"},
    "quest_add_epilogue":{"quest_id":"story","new_stage_id":"epilogue","objective":"The far horizon"},
    "quest_extend_terminal":{"quest_id":"story","stage_id":"endingA","new_stage_id":"again","objective":"Again"},
    "quest_fork_terminal":{"quest_id":"story","stage_id":"endingA","prefix":"branch",
                           "objectives":["Save the city","Travel by sea"]},
    "quest_bridge_endings":{"quest_id":"story","new_stage_id":"reunion","objective":"Reunite"},
    "quest_detour_leaf":{"quest_id":"story","stage_id":"first","new_stage_id":"secret","objective":"Hidden path"},
    "quest_stage_reparent":{"quest_id":"story","stage_id":"endingA","new_parent_id":"side"},
    "quest_swap_branches":{"quest_id":"story","stage_a":"middle","stage_b":"side"},
    "quest_order_choices":{"quest_id":"story","stage_id":"middle","choices":["endingB","endingA"]},
    "quest_backfill_objectives":{"quest_id":"story","prefix":"Chapter"},
    "quest_template_sequence":{"quest_id":"story","stage_id":"endingA","prefix":"act",
                               "count":4,"objective":"Proceed"},
    "quest_template_binary_tree":{"quest_id":"story","stage_id":"endingA","prefix":"choice",
                                  "depth":2,"objective":"Discover"},
    "quest_stage_cleanup":{"quest_id":"story","stage_id":"detour"},
    "quest_mirror_branch":{"quest_id":"story","stage_id":"endingA","parent_stage_id":"side",
                           "prefix":"mirror"},
    "quest_convert_to_linear":{"quest_id":"story",
                               "stage_order":["first","middle","side","detour","endingA","endingB"]},
    "event_stage_dialogue":{"event_id":"dialogue","target":"merchant","value":"The citadel awaits"},
    "event_stage_flag":{"event_id":"flag","target":"chapter_reached","value":"true"},
    "event_stage_cutscene":{"event_id":"cinematic","target":"intro","value":"camera_pan"},
    "event_stage_music":{"event_id":"music","target":"theme","value":"exploration"},
    "event_stage_item":{"event_id":"loot","target":"merchant","value":"potion"},
    "event_stage_camera":{"event_id":"camera","target":"hero","value":"closeup"},
    "event_stage_portal":{"event_id":"portal","target":"gateway","value":"sky_island"},
    "event_trigger_promote":{"event_id":"opening","trigger":"quest"},
    "event_flag_gate":{"event_id":"opening","flag":"started","expected":True},
    "event_mass_duplicate":{"source_event_ids":["opening"],"prefix":"act"},
}

SENSOR={name:{"page_id":name+"_01"} for name in SENSOR_ACTIONS}
PAGE={
    "page_condition_copy":{"page_id":"weather_rise","source_index":0},
    "page_action_copy":{"page_id":"weather_rise","source_index":0},
    "page_condition_swap":{"page_id":"weather_rise","a":0,"b":1},
    "page_action_swap":{"page_id":"weather_rise","a":0,"b":1},
    "page_condition_rotate":{"page_id":"weather_rise","offset":1},
    "page_action_rotate":{"page_id":"weather_rise","offset":1},
    "page_threshold_shift":{"page_id":"weather_rise","delta":3},
    "page_threshold_scale":{"page_id":"weather_rise","factor":2},
    "page_duplicate_signal":{"page_id":"weather_rise","new_page_id":"altitude_gate",
                             "signal":"altitude_m","comparison":"above","threshold":55},
    "page_dual_threshold_branches":{"page_id":"weather_rise",
                                   "low_page_id":"cold_side","high_page_id":"hot_side",
                                   "low":10,"high":50},
}
CASES={**TOPOLOGY,**ACTORS,**STORY,**SENSOR,**PAGE}
assert len(CASES)==100


class HundredNewRealGameplayTools(unittest.TestCase):
    def test_250_distinct_real_editor_tools_registered(self):
        self.assertGreaterEqual(len(AUTHORING_ACTIONS),250)
        self.assertEqual(len(AUTHORING_ACTIONS),len(set(AUTHORING_ACTIONS)))
        self.assertEqual(set(CASES),set(AUTHORING_ACTIONS[150:250]))

    def test_sensors_are_consummable_by_canonical_rpg_simulator(self):
        authored=execute_authoring(project(),"sensor_wind_gust",SENSOR["sensor_wind_gust"])
        sensor=authored.environmental_pages[-1]
        observed=evaluate_environment_events((sensor,),current={"wind_mps":25},now_ms=1000)
        self.assertEqual(1,len(observed.accepted))
        self.assertEqual(sensor.page_id,observed.accepted[0].page_id)
        self.assertEqual("set_flag",observed.accepted[0].actions[0].kind)

    def test_batch_persists_actual_game_source_with_roundtrip(self):
        original=project()
        changed=apply_authoring_batch(original,[
            {"action":"terrain_bezier_road","parameters":TOPOLOGY["terrain_bezier_road"]},
            {"action":"actors_shift_altitude","parameters":ACTORS["actors_shift_altitude"]},
            {"action":"quest_add_prologue","parameters":STORY["quest_add_prologue"]},
            {"action":"sensor_wind_gust","parameters":SENSOR["sensor_wind_gust"]},
        ])
        result=changed["project"]
        self.assertNotEqual(project_digest(original),project_digest(result))
        roundtrip=load_authored_document(authored_document(result),project_id="testgame")
        self.assertEqual(project_digest(result),project_digest(roundtrip))
        self.assertEqual(len(result.placements),len(roundtrip.placements))
        self.assertEqual(result.layers[0].data,roundtrip.layers[0].data)
        self.assertEqual(result.environmental_pages,roundtrip.environmental_pages)
        self.assertEqual(result.native_quests,roundtrip.native_quests)

    def test_native_quest_graph_is_playable_after_branch(self):
        changed=execute_authoring(project(),"quest_fork_terminal",STORY["quest_fork_terminal"])
        graph=compile_studio_native_quest_graph(changed)
        self.assertGreater(len(graph["quests"][0]["stages"]),6)

    def test_immutable_source_rejected_after_invalid_quest_change(self):
        original=project()
        digest=project_digest(original)
        with self.assertRaises(StudioError):
            apply_authoring_batch(original,[
                {"action":"terrain_diamond_landmass",
                 "parameters":TOPOLOGY["terrain_diamond_landmass"]},
                {"action":"quest_stage_reparent",
                 "parameters":{"quest_id":"story","stage_id":"first",
                               "new_parent_id":"endingA"}},
            ])
        self.assertEqual(digest,project_digest(original))

    def test_archipelago_bridges_connect_actually_walkable_floor(self):
        authored=execute_authoring(
            project(),"terrain_archipelago_bridges",
            TOPOLOGY["terrain_archipelago_bridges"])
        layer=authored.layers[0]
        import collections
        start=(0,0)
        discovered={start}
        queue=collections.deque([start])
        while queue:
            x,y=queue.popleft()
            for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if (0<=nx<12 and 0<=ny<12
                        and (nx,ny) not in discovered
                        and layer.data[ny*layer.width+nx]==0):
                    discovered.add((nx,ny))
                    queue.append((nx,ny))
        self.assertIn((9,0),discovered)

    def test_castle_moat_has_blocked_moat_and_walkable_causeway(self):
        authored=execute_authoring(
            project(),"terrain_moat_castle",TOPOLOGY["terrain_moat_castle"])
        layer=authored.layers[0]
        self.assertEqual(0,layer.data[6*layer.width+10])
        self.assertEqual(1,layer.data[7*layer.width+10])

    def test_actor_copies_preserve_source_index_bindings(self):
        changed=execute_authoring(project(),"actors_clone_selected",ACTORS["actors_clone_selected"])
        original=project()
        self.assertEqual(original.placements,changed.placements[:len(original.placements)])
        self.assertGreater(len(changed.placements),len(original.placements))


def _actual_change(name,params):
    def check(self):
        original=project()
        changed=execute_authoring(original,name,params)
        self.assertIsInstance(changed,StudioProject)
        self.assertNotEqual(project_digest(original),project_digest(changed),
                            "tool did not actually author game content: "+name)
        self.assertEqual(project_digest(original),project_digest(project()))
        self.assertEqual(original.project_id,changed.project_id)
    return check


for _name,_params in CASES.items():
    setattr(HundredNewRealGameplayTools,"test_real_"+_name,
            _actual_change(_name,_params))

if __name__=="__main__":
    unittest.main()
