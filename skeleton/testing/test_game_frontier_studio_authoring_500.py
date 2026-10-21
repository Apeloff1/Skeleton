"""Functional tests for Forge Studio's five new families / 250 production tools.

Every named test checks ACTUAL typed-source mutation, not a registry flag.
Additional integration scenarios validate canonical project persistence,
native quest graph creation, playable NPC interactions, RPG event evaluation,
batch atomicity, deterministic content and original-game Godot export.
"""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioProject, MapLayer, compile_studio_expedition,
    compile_studio_native_quest_graph,
)
from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, execute_authoring, apply_authoring_batch, project_digest,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.forge.game_frontier_studio_biome_factory import BIOME_ACTIONS
from skeleton.forge.game_frontier_studio_structure_factory import STRUCTURE_ACTIONS
from skeleton.forge.game_frontier_studio_encounter_factory import ENCOUNTER_ACTIONS
from skeleton.forge.game_frontier_studio_quest_blueprint_factory import (
    QUEST_BLUEPRINT_ACTIONS,
)
from skeleton.forge.game_frontier_studio_reactive_scene_factory import (
    REACTIVE_SCENE_ACTIONS,
)
from skeleton.testing.test_game_frontier_studio_authoring import project as minimal_project


def original_project() -> StudioProject:
    baseline=minimal_project()
    data=tuple((x*3+y*5)%3 for y in range(16) for x in range(16))
    map_layer=MapLayer("biome",16,16,("floor","wall","water"),data)
    return replace(baseline,layers=(map_layer,)+baseline.layers)


BIOME_CASES={
    action:{"layer":"biome","x":0,"y":0,"width":16,"height":16,
            "floor":0,"wall":1,"seed":47,"threshold":.53,"scale":5}
    for action in BIOME_ACTIONS
}
STRUCTURE_CASES={
    action:{"layer":"biome","x":0,"y":0,"width":16,"height":16,
            "floor":0,"wall":1,"seed":47}
    for action in STRUCTURE_ACTIONS
}
ENCOUNTER_CASES={
    action:{"prefab_id":"merchant","count":4,"x":8,"y":8,"z":0,
            "event_prefix":"encounter_fixture","seed":47,"radius":5,"spacing":2,
            "dialogue":"I have a story from this world"}
    for action in ENCOUNTER_ACTIONS
}
QUEST_CASES={
    action:{"quest_id":"arc_"+action[6:],"event_id":"starter_"+action[6:]}
    for action in QUEST_BLUEPRINT_ACTIONS
}
REACTIVE_CASES={
    action:{"page_id":"rpg_"+action,"priority":10,"cooldown_ms":1000}
    for action in REACTIVE_SCENE_ACTIONS
}
CASES={**BIOME_CASES,**STRUCTURE_CASES,**ENCOUNTER_CASES,**QUEST_CASES,**REACTIVE_CASES}
assert len(CASES)==250


class FiveHundredProductionAcceptance(unittest.TestCase):
    def test_registry_contains_all_500_executable_operators(self):
        self.assertGreaterEqual(len(AUTHORING_ACTIONS),500)
        self.assertEqual(len(AUTHORING_ACTIONS),len(set(AUTHORING_ACTIONS)))
        self.assertEqual(set(CASES),set(AUTHORING_ACTIONS[250:500]))

    def test_all_fifty_biome_recipes_are_replay_deterministic(self):
        base=original_project()
        for name in BIOME_ACTIONS:
            with self.subTest(action=name):
                one=execute_authoring(base,name,BIOME_CASES[name])
                two=execute_authoring(base,name,BIOME_CASES[name])
                self.assertEqual(one.layers[0].data,two.layers[0].data)
                self.assertNotEqual(one.layers[0].data,base.layers[0].data)

    def test_interactive_creatures_have_real_placed_actor_event_links(self):
        source=original_project()
        result=execute_authoring(source,"encounter_sky_pirates",
                                 ENCOUNTER_CASES["encounter_sky_pirates"])
        new_actors=result.placements[len(source.placements):]
        events=result.events[len(source.events):]
        self.assertEqual(4,len(new_actors))
        self.assertEqual(4,len(events))
        for i,e in enumerate(events):
            self.assertEqual("show_dialogue",e.action)
            self.assertEqual("interact",e.trigger)
            self.assertEqual("merchant:"+str(len(source.placements)+i),e.target)
        self.assertTrue(any(p.z>0 for p in new_actors))

    def test_native_quest_templates_include_player_choices_and_game_events(self):
        source=original_project()
        result=execute_authoring(source,"quest_sky_island_rescue",
                                 QUEST_CASES["quest_sky_island_rescue"])
        new=result.native_quests[-1]
        self.assertEqual(6,len(new.stages))
        self.assertTrue(any(len(s.next_stage_ids)>1 for s in new.stages))
        self.assertEqual("start_quest",result.events[-1].action)
        self.assertEqual(new.quest_id,result.events[-1].value)
        graph=compile_studio_native_quest_graph(result)
        self.assertGreater(len(graph["quests"]),len(source.native_quests))

    def test_environmental_reactions_fire_from_real_canonical_sensor_evaluator(self):
        source=original_project()
        result=execute_authoring(source,"reaction_storm_warning",
                                 REACTIVE_CASES["reaction_storm_warning"])
        page=result.environmental_pages[-1]
        current={"wind_mps":24,"rain_mm_h":8}
        triggered=evaluate_environment_events((page,),current=current,now_ms=5000)
        self.assertEqual(1,len(triggered.accepted))
        self.assertEqual("show_dialogue",triggered.accepted[0].actions[0].kind)
        silenced=evaluate_environment_events((page,),
            current={"wind_mps":1,"rain_mm_h":0},now_ms=5000)
        self.assertEqual(0,len(silenced.accepted))

    def test_mixed_5_family_batch_roundtrips_typed_game_project(self):
        base=original_project()
        request=[
            {"action":"terrain_floating_islands",
             "parameters":BIOME_CASES["terrain_floating_islands"]},
            {"action":"structure_portal_plaza",
             "parameters":STRUCTURE_CASES["structure_portal_plaza"]},
            {"action":"encounter_cloud_drakes",
             "parameters":ENCOUNTER_CASES["encounter_cloud_drakes"]},
            {"action":"quest_sky_island_rescue",
             "parameters":QUEST_CASES["quest_sky_island_rescue"]},
            {"action":"reaction_storm_warning",
             "parameters":REACTIVE_CASES["reaction_storm_warning"]},
        ]
        result=apply_authoring_batch(base,request)
        changed=result["project"]
        self.assertEqual(5,result["receipt"]["action_count"])
        self.assertNotEqual(project_digest(base),project_digest(changed))
        document=authored_document(changed)
        recovered=load_authored_document(document,project_id="testgame")
        self.assertEqual(project_digest(changed),project_digest(recovered))
        self.assertEqual(changed.layers[0].data,recovered.layers[0].data)
        self.assertEqual(changed.placements,recovered.placements)
        self.assertEqual(changed.native_quests,recovered.native_quests)
        self.assertEqual(changed.environmental_pages,recovered.environmental_pages)
        self.assertEqual(project_digest(base),project_digest(original_project()))

    def test_invalid_step_rolls_back_earlier_real_edits(self):
        base=original_project()
        before=project_digest(base)
        with self.assertRaises(StudioError):
            apply_authoring_batch(base,[
                {"action":"terrain_lighthouse_blackout",
                 "parameters":BIOME_CASES["terrain_floating_islands"]},
            ])
        self.assertEqual(before,project_digest(base))
        with self.assertRaises(StudioError):
            apply_authoring_batch(base,[
                {"action":"encounter_cloud_drakes",
                 "parameters":ENCOUNTER_CASES["encounter_cloud_drakes"]},
                {"action":"quest_sky_island_rescue",
                 "parameters":{"quest_id":"welcome","event_id":"collision"}},
            ])
        self.assertEqual(before,project_digest(base))

    def test_original_game_compiler_consumes_quest_actors_and_maps(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        base=original_project()
        composed=apply_authoring_batch(base,[
            {"action":"structure_dungeon_rooms",
             "parameters":STRUCTURE_CASES["structure_dungeon_rooms"]},
            {"action":"encounter_labyrinth_wardens",
             "parameters":ENCOUNTER_CASES["encounter_labyrinth_wardens"]},
            {"action":"quest_ruins_of_ash",
             "parameters":QUEST_CASES["quest_ruins_of_ash"]},
        ])["project"]
        native=compile_studio_expedition(
            composed,ArchipelagoProfile(seed=41,islands=4,caverns=0,
                                         include_portals=False,include_underwater=False),
            include_godot=True,playtest_routes=2)
        self.assertGreater(native["waypoints"],4)
        self.assertIn("game/frontier/studio_terrain.gd",native["godot_project_files"])
        self.assertIn("game/frontier/studio_terrain.json",native["godot_project_files"])
        self.assertGreater(len(native["godot_project_files"]),2)

    def test_reaction_requires_valid_sensor_conditions(self):
        source=original_project()
        with self.assertRaises((StudioError,ValueError)):
            execute_authoring(source,"reaction_storm_warning",{
                **REACTIVE_CASES["reaction_storm_warning"],
                "thresholds":["not-numeric",4],
            })


def _source_change(name,params):
    def test(self):
        original=original_project()
        before=project_digest(original)
        updated=execute_authoring(original,name,params)
        self.assertIsInstance(updated,StudioProject)
        self.assertNotEqual(before,project_digest(updated),
                            "operation did not actually author playable game content: "+name)
        self.assertEqual(before,project_digest(original))
    return test


for _name,_params in CASES.items():
    setattr(FiveHundredProductionAcceptance,"test_real_"+_name,_source_change(_name,_params))


if __name__=="__main__":
    unittest.main()
