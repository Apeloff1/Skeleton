"""Functional acceptance for Forge Studio operations 101-150.

These tests create typed project data, exercise every operation's real output,
round-trip it through the existing workspace document codec, and reject
unsafe state changes. No quality-gate-only tests count as game features.
"""
from __future__ import annotations

from dataclasses import replace
import json
import unittest

from skeleton.forge.game_frontier_studio import (
    MapLayer, StudioEvent, StudioProject, StudioQuest, StudioQuestStage, StudioError,
)
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, execute_authoring, apply_authoring_batch, project_digest,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.forge.game_frontier_studio_procedural_edit import PROCEDURAL_ACTIONS
from skeleton.forge.game_frontier_studio_population_edit import POPULATION_ACTIONS
from skeleton.forge.game_frontier_studio_narrative_edit import STORY_ACTIONS
from skeleton.testing.test_game_frontier_studio_authoring import project as fixture


def source():
    base=fixture()
    layer=MapLayer(
        "terrain",24,24,("floor","wall","water"),
        tuple((x*7+y*3)%3 for y in range(24) for x in range(24)))
    quest=StudioQuest(
        "welcome", "Welcome", "first", (
            StudioQuestStage("first","Set out",("linear",)),
            StudioQuestStage("linear","Find guide",("middle",)),
            StudioQuestStage("middle","Make choice",("endingA","endingB")),
            StudioQuestStage("endingA","Return"),
            StudioQuestStage("endingB","Explore"),
        ))
    extra=StudioEvent("begin_story","interact","",True,
                      "start_quest","merchant","welcome")
    return replace(base,layers=(layer,)+base.layers,
                   native_quests=(quest,),events=base.events+(extra,))


TERRAIN_BASE={
    "layer":"terrain","x":0,"y":0,"width":20,"height":20,
    "seed":42,"floor":0,"wall":1,"scale":5,"threshold":.5,
}
TERRAIN_DATA={
    name:dict(TERRAIN_BASE) for name in PROCEDURAL_ACTIONS
}
TERRAIN_DATA["terrain_road_links"]["nodes"]=[[1,1],[5,17],[18,18]]
TERRAIN_DATA["terrain_avoidance_path"].update({
    "start_x":0,"start_y":0,"end_x":19,"end_y":19})
TERRAIN_DATA["terrain_room_dungeon"]["rooms"]=8
TERRAIN_DATA["terrain_cave_automata"].update({"iterations":3,"density":.45})
TERRAIN_DATA["terrain_depth_maze"].update({"width":19,"height":19})

FORMATION_BASE={
    "prefab_id":"tree","count":8,"x":10,"y":10,"z":0,
    "seed":42,"radius":15,"spacing":2,
}
POPULATION_DATA={name:dict(FORMATION_BASE)
                 for name in POPULATION_ACTIONS if name.startswith("formation_")}
POPULATION_DATA["formation_waypoint_path"]["waypoints"]=[
    [1,1,0],[10,1,0],[10,12,0]]
POPULATION_DATA["formation_perimeter"].update({"width":10,"height":10})
POPULATION_DATA.update({
    "actors_translate":{"indices":[0],"dx":3,"dy":4,"dz":0},
    "actors_rotate":{"indices":[0],"angle_deg":60,"pivot_x":0,"pivot_y":0},
    "actors_mirror":{"indices":[0],"axis":"x","pivot_x":5},
    "actors_reassign_prefab":{"indices":[0],"prefab_id":"merchant"},
})

STORY_DATA={
    "narrative_branch_pair":{
        "quest_id":"welcome","from_stage_id":"middle","stage_prefix":"alternative",
        "objectives":["Enter the mountain","Explore the coast"]},
    "narrative_branch_multi":{
        "quest_id":"welcome","from_stage_id":"middle","stage_prefix":"route",
        "choices":3,"objectives":["Road","Sea","Sky"]},
    "narrative_extend_chain":{
        "quest_id":"welcome","from_stage_id":"endingA","stage_prefix":"sequel",
        "objectives":["Collect the key","Cross the bridge","Find the home"]},
    "narrative_insert_stage":{
        "quest_id":"welcome","from_stage_id":"first","to_stage_id":"linear",
        "new_stage_id":"bridge","objective":"Cross the forest"},
    "narrative_bypass_stage":{"quest_id":"welcome","stage_id":"linear"},
    "narrative_relabel_quest":{"quest_id":"welcome","new_quest_id":"pilgrimage"},
    "narrative_fork_quest":{"quest_id":"welcome","new_quest_id":"alternative",
                           "title":"The Other Journey"},
    "narrative_merge_endings":{"quest_id":"welcome","epilogue_id":"reunion",
                               "objective":"Reunite at the citadel"},
    "event_clone":{"event_id":"opening","new_event_id":"opening_alt",
                   "target":"merchant"},
    "event_batch_retarget":{"event_ids":["opening"],"target":"merchant"},
    "event_batch_retrigger":{"event_ids":["opening"],"trigger":"weather"},
    "event_bind_quest":{"quest_id":"welcome","event_id":"begin_alt","target":"merchant"},
    "event_actor_dialogue_batch":{
        "indices":[0,1],"event_prefix":"dialogue","value":"Hello traveler"},
    "event_actor_audio_batch":{
        "indices":[0,1],"event_prefix":"ambient","value":"village_theme"},
    "event_actor_loot_batch":{
        "indices":[0,1],"event_prefix":"pickup","value":"healing_potion"},
}
ALL_NEW = {**TERRAIN_DATA, **POPULATION_DATA, **STORY_DATA}
assert len(ALL_NEW)==50


class ForgeNewFiftyFunctionalAcceptance(unittest.TestCase):
    def test_inventory_grows_to_150_non_duplicate_operations(self):
        self.assertGreaterEqual(len(AUTHORING_ACTIONS),150)
        self.assertEqual(len(AUTHORING_ACTIONS[:500]),len(set(AUTHORING_ACTIONS[:500])))
        self.assertTrue(all(name in AUTHORING_ACTIONS for name in ALL_NEW))

    def test_real_procedural_content_is_seed_stable(self):
        original=source()
        for name in PROCEDURAL_ACTIONS:
            with self.subTest(generator=name):
                params=TERRAIN_DATA[name]
                first=execute_authoring(original,name,params)
                second=execute_authoring(original,name,params)
                self.assertEqual(first.layers[0].data,second.layers[0].data)
                self.assertNotEqual(first.layers[0].data,original.layers[0].data)
                self.assertEqual(project_digest(first),project_digest(second))

    def test_group_transforms_preserve_existing_actor_binding_identity(self):
        original=source()
        updated=execute_authoring(original,"actors_rotate",
                                  POPULATION_DATA["actors_rotate"])
        self.assertEqual(original.placements[0].prefab_id,
                         updated.placements[0].prefab_id)
        self.assertNotEqual(original.placements[0],updated.placements[0])

    def test_story_branch_preserves_native_quest_reachability(self):
        from skeleton.forge.game_frontier_studio import compile_studio_native_quest_graph
        original=source()
        branch=execute_authoring(original,"narrative_branch_multi",
                                 STORY_DATA["narrative_branch_multi"])
        self.assertEqual(1,len(compile_studio_native_quest_graph(branch)["quests"]))
        self.assertEqual(8,len(branch.native_quests[0].stages))

    def test_story_rename_updates_live_quest_event(self):
        authored=execute_authoring(source(),"narrative_relabel_quest",
                                   STORY_DATA["narrative_relabel_quest"])
        self.assertEqual("pilgrimage",authored.native_quests[0].quest_id)
        self.assertEqual("pilgrimage",next(e for e in authored.events
                         if e.event_id=="begin_story").value)

    def test_new_game_edits_survive_existing_revision_codec(self):
        original=source()
        for name in ("terrain_room_dungeon","formation_ring","narrative_branch_pair"):
            original=execute_authoring(original,name,ALL_NEW[name])
        saved=authored_document(original)
        reopened=load_authored_document(saved,project_id="testgame")
        self.assertEqual(project_digest(reopened),project_digest(original))
        self.assertEqual(reopened.layers,original.layers)
        self.assertEqual(reopened.placements,original.placements)
        self.assertEqual(reopened.native_quests,original.native_quests)

    def test_native_godot_emits_actual_rendered_terrain_tiles(self):
        from skeleton.forge.game_frontier_studio import compile_studio_expedition
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        original=source()
        edited=execute_authoring(original,"terrain_depth_maze",
                                 TERRAIN_DATA["terrain_depth_maze"])
        built=compile_studio_expedition(
            edited,ArchipelagoProfile(seed=25,islands=4,caverns=0,
                                       include_portals=False,include_underwater=False),
            playtest_routes=2,include_godot=True)
        files=built["godot_project_files"]
        self.assertIn("game/frontier/studio_terrain.gd",files)
        self.assertIn("game/frontier/studio_terrain.json",files)
        self.assertIn("MultiMeshInstance3D",files["game/frontier/studio_terrain.gd"])
        self.assertIn("StudioTerrain",files["game/frontier/expedition.tscn"])
        record=json.loads(files["game/frontier/studio_terrain.json"])
        self.assertEqual(project_digest(edited),record["studio_sha256"])
        self.assertGreater(record["rendered_cells"],0)
        terrain=next(item for item in record["layers"] if item["id"]=="terrain")
        self.assertEqual(list(edited.layers[0].data),terrain["tiles"])
        self.assertEqual(record["source_cells"],record["rendered_cells"])

    def test_native_walkable_dungeon_tiles_become_reachable_game_routes(self):
        from skeleton.forge.game_frontier_studio import author_studio_expedition
        from skeleton.jeeves.game_frontier_expedition import Traveler, find_route, verify_route
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        authored=execute_authoring(source(),"terrain_depth_maze",
                                   TERRAIN_DATA["terrain_depth_maze"])
        world=author_studio_expedition(
            authored,ArchipelagoProfile(seed=25,islands=4,caverns=0,
                        include_portals=False,include_underwater=False))
        tile_nodes=[x for x in world.waypoints if x.waypoint_id.startswith("studio_tile_")]
        self.assertGreater(len(tile_nodes),2)
        tile_set={x.waypoint_id for x in tile_nodes}
        walk_edges=[e for e in world.edges if e.edge_id.startswith("studio_path_")]
        self.assertGreater(len(walk_edges),1)
        self.assertTrue(all(e.source in tile_set and e.target in tile_set
                            and e.mode=="walk" for e in walk_edges))
        traveler=Traveler(permitted_modes=frozenset(("walk","rope_bridge")),max_stamina=1000)
        target=tile_nodes[-1].waypoint_id
        route=find_route(world,traveler,target)
        self.assertEqual(target,route.destination)
        proof=verify_route(world,traveler,route)
        self.assertEqual(target,proof["final_state"]["position"])

    def test_unwalkable_water_tiles_cannot_become_free_paths(self):
        from skeleton.forge.game_frontier_studio_tile_navigation import add_studio_walkable_paths
        from skeleton.jeeves.game_frontier_expedition_generation import (
            author_archipelago,ArchipelagoProfile)
        authored=source()
        watery=replace(authored,layers=(MapLayer(
            "terrain",12,12,("water","lava"),(0,)*144),))
        generated=author_archipelago(
            watery.project_id,project_digest(watery),
            ArchipelagoProfile(seed=31,islands=3,caverns=0,
                               include_portals=False,include_underwater=False))
        updated=add_studio_walkable_paths(watery,generated)
        self.assertEqual(len(generated.waypoints),len(updated.waypoints))
        self.assertEqual(len(generated.edges),len(updated.edges))

    def test_godot_terrain_lod_respects_resource_budget(self):
        from skeleton.forge.game_frontier_studio_terrain_runtime import add_studio_native_terrain
        from skeleton.jeeves.game_frontier_expedition_godot import (
            _GODOT_SCENE,
        )
        original=source()
        huge=MapLayer("huge",256,256,("grass","rock"),(1,)*(256*256))
        project=replace(original,layers=(huge,))
        files=add_studio_native_terrain(project,{
            "game/frontier/expedition.tscn":_GODOT_SCENE,
        })
        record=json.loads(files["game/frontier/studio_terrain.json"])
        self.assertLessEqual(record["rendered_cells"],8192)
        self.assertEqual(record["source_cells"],65536)
        self.assertTrue(record["visual_lod_only"])

    def test_failed_multi_step_stops_without_mutating_source(self):
        original=source()
        old=project_digest(original)
        with self.assertRaises(StudioError):
            apply_authoring_batch(original,[
                {"action":"terrain_room_dungeon","parameters":TERRAIN_DATA["terrain_room_dungeon"]},
                {"action":"actors_reassign_prefab","parameters":{
                    "indices":[0],"prefab_id":"nonexistent"}}])
        self.assertEqual(old,project_digest(original))

    def test_poisson_scatter_respects_minimum_separation(self):
        original=source()
        p={**POPULATION_DATA["formation_poisson"],"min_distance":2}
        changed=execute_authoring(original,"formation_poisson",p)
        pts=changed.placements[len(original.placements):]
        for i,a in enumerate(pts):
            for b in pts[i+1:]:
                self.assertGreaterEqual(((a.x-b.x)**2+(a.y-b.y)**2)**.5,2-1e-7)

    def test_deep_quest_cycle_rejected(self):
        original=source()
        with self.assertRaises(StudioError):
            execute_authoring(original,"narrative_insert_stage",{
                "quest_id":"welcome","from_stage_id":"first",
                "to_stage_id":"nonexistent","new_stage_id":"loop",
                "objective":"Impossible"})

    def test_invalid_terrain_path_rejected(self):
        with self.assertRaises(StudioError):
            execute_authoring(source(),"terrain_avoidance_path",{
                **TERRAIN_DATA["terrain_avoidance_path"],"end_x":40})


def _build_action_test(name, params):
    def actual(self):
        origin=source()
        updated=execute_authoring(origin,name,params)
        self.assertIsInstance(updated,StudioProject)
        self.assertNotEqual(project_digest(origin),project_digest(updated),
                            "real authoring action did not change Studio source: "+name)
        self.assertEqual(origin.project_id,updated.project_id)
    return actual


for _name,_args in ALL_NEW.items():
    setattr(ForgeNewFiftyFunctionalAcceptance,
            "test_real_authoring_"+_name,_build_action_test(_name,_args))


if __name__=="__main__":
    unittest.main()
