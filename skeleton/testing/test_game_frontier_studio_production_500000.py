"""Real-function qualification for 450,000 lazy-indexed directed productions.

Checks arithmetic catalog lookup without eager startup materialization, every
one of the 45,000 base recipe contracts with all 10 legal production directors,
typed source editing for 10 director × 10 domain combinations, and concrete
native game, NPC, quest, RPG and persistence behavior. These are executable
composed workflows, not 450,000 independent algorithms or games.
"""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioProject, compile_studio_expedition,
    compile_studio_native_quest_graph,
)
from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, apply_authoring_batch, authored_summary,
    execute_authoring, project_digest,
)
from skeleton.forge.game_frontier_studio_directed_production import (
    DIRECTED_ACTIONS, DIRECTORS, DIRECTOR_PURPOSES,
    describe_direction, search_directions,
)
from skeleton.forge.game_frontier_studio_system_expansions import (
    EXPANDED_RECIPE_ACTIONS, GAMEPLAY_LAYERS,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project, arguments,
)


class FiveHundredThousandSourceProductions(unittest.TestCase):
    def test_catalog_is_virtual_500k_and_stable(self):
        self.assertGreaterEqual(len(AUTHORING_ACTIONS),500000)
        self.assertEqual(450000,len(DIRECTED_ACTIONS))
        self.assertEqual(10,len(DIRECTORS))
        self.assertEqual(AUTHORING_ACTIONS[50000],DIRECTED_ACTIONS[0])
        self.assertEqual(AUTHORING_ACTIONS[499999],DIRECTED_ACTIONS[-1])
        self.assertEqual(AUTHORING_ACTIONS[50000:50050],
                         DIRECTED_ACTIONS[:50])
        self.assertTrue(AUTHORING_ACTIONS[-1] in AUTHORING_ACTIONS)
        self.assertNotIn("direct_trusted_python_exec____player_agency",
                         AUTHORING_ACTIONS)
        with self.assertRaises(IndexError):
            _=DIRECTED_ACTIONS[450000]

    def test_all_450000_names_are_reversible_arithmetic_plans(self):
        seen=set()
        # Each existing, exact 45k registered expansion combines with exactly
        # 10 real production director implementations.
        for base_idx, base in enumerate(EXPANDED_RECIPE_ACTIONS):
            stem="direct_"+base.removeprefix("expand_")+"____"
            for i,director in enumerate(DIRECTORS):
                name=DIRECTED_ACTIONS[base_idx*10+i]
                self.assertEqual(stem+director,name)
                self.assertIn(name,DIRECTED_ACTIONS)
                seen.add(name)
        self.assertEqual(450000,len(seen))
        self.assertEqual(450000,len(DIRECTED_ACTIONS))

    def test_ten_directors_mutate_source_for_ten_production_domains(self):
        base=original_project()
        before=project_digest(base)
        for domain in range(10):
            produced=set()
            for director in range(10):
                action=DIRECTED_ACTIONS[domain*45000+director]
                with self.subTest(domain=domain,director=DIRECTORS[director]):
                    edited=execute_authoring(base,action,arguments(action))
                    self.assertIsInstance(edited,StudioProject)
                    self.assertNotEqual(before,project_digest(edited))
                    self.assertGreater(len(edited.environmental_pages),
                                       len(base.environmental_pages))
                    produced.add(project_digest(edited))
            self.assertEqual(10,len(produced),
                "all ten directors need a distinct actually-authored game state")
        self.assertEqual(before,project_digest(base))

    def test_all_500_source_blueprints_execute_with_directed_game_changes(self):
        original=original_project()
        before=project_digest(original)
        for domain in range(10):
            for index in range(50):
                action=DIRECTED_ACTIONS[domain*45000 + index*900]
                with self.subTest(source=action):
                    authored=execute_authoring(original,action,arguments(action))
                    self.assertNotEqual(before,project_digest(authored))
                    self.assertGreater(len(authored.environmental_pages),
                                       len(original.environmental_pages))
        self.assertEqual(before,project_digest(original_project()))

    def test_real_directed_event_matches_two_independent_observed_sensors(self):
        base=original_project()
        action=DIRECTED_ACTIONS[0]
        result=execute_authoring(base,action,arguments(action))
        page=result.environmental_pages[-1]
        self.assertEqual(2,len(page.conditions))
        self.assertEqual("set_flag",page.actions[0].kind)
        signals={c.signal for c in page.conditions}
        self.assertEqual({"compass_heading_deg","rain_mm_h"},signals)
        accepted=evaluate_environment_events(
            (page,),current={"compass_heading_deg":150,"rain_mm_h":5},
            now_ms=20000)
        self.assertEqual(1,len(accepted.accepted))
        rejected=evaluate_environment_events(
            (page,),current={"compass_heading_deg":0,"rain_mm_h":0},
            now_ms=20000)
        self.assertEqual(0,len(rejected.accepted))

    def test_existing_cast_is_untouched_but_new_interactive_cast_is_directed(self):
        base=original_project()
        action=DIRECTED_ACTIONS[2*45000+7]
        result=execute_authoring(base,action,arguments(action))
        self.assertEqual(base.placements,result.placements[:len(base.placements)])
        self.assertEqual(len(base.placements)+4,len(result.placements))
        self.assertEqual(len(base.events)+4,len(result.events))
        self.assertTrue(any(a.z>0 for a in result.placements[len(base.placements):]))

    def test_original_story_gets_a_reachable_directed_side_stage(self):
        base=original_project()
        action=DIRECTED_ACTIONS[3*45000+8]
        edited=execute_authoring(base,action,arguments(action))
        quest=edited.native_quests[-1]
        directed=[x for x in quest.stages if "_dir_" in x.stage_id]
        self.assertEqual(1,len(directed))
        self.assertEqual(1,len(directed[0].next_stage_ids))
        self.assertIn(directed[0].stage_id,quest.stages[0].next_stage_ids)
        result=compile_studio_native_quest_graph(edited)
        self.assertTrue(result["quests"])

    def test_search_pages_filter_director_domain_and_system(self):
        result=search_directions(domain="stronghold",
                                 system_layer="stealth",
                                 director="physics_obstacles",limit=13)
        self.assertEqual(450000,result["total_catalog"])
        self.assertEqual(450,result["matched"])
        self.assertEqual(13,len(result["items"]))
        self.assertTrue(all(item["direction"]=="physics_obstacles" for item in result["items"]))
        next_page=search_directions(domain="stronghold",
                                 system_layer="stealth",
                                 director="physics_obstacles",
                                 offset=13,limit=13)
        self.assertFalse({p["operation"] for p in result["items"]} &
                         {p["operation"] for p in next_page["items"]})
        with self.assertRaises(StudioError):
            search_directions(director="__import__")
        with self.assertRaises(StudioError):
            search_directions(limit=999)

    def test_arithmetic_pagination_matches_exact_virtual_registry(self):
        for offset in (0,1,31,1024,123456,449968,449999):
            with self.subTest(offset=offset):
                result=search_directions(offset=offset,limit=32)
                expected=DIRECTED_ACTIONS[offset:min(offset+32,450000)]
                self.assertEqual(
                    expected,
                    tuple(item["operation"] for item in result["items"]))
                self.assertEqual(450000,result["matched"])
        selected=search_directions(
            domain="stronghold",system_layer="stealth",
            director="physics_obstacles",offset=123,limit=4)
        self.assertEqual(450,selected["matched"])
        expected=[]
        for n in range(123,127):
            # stronghold domain index 7; every recipe has 10 system-layer
            # expansions; stealth index 6 and physics director index 6.
            index=((7*450+n)*10+6)*10+6
            expected.append(DIRECTED_ACTIONS[index])
        self.assertEqual(expected,[
            item["operation"] for item in selected["items"]])
        self.assertEqual([],search_directions(
            domain="stronghold",system_layer="stealth",
            director="physics_obstacles",offset=451,limit=7)["items"])

    def test_replay_determinism_and_immutable_transaction(self):
        base=original_project()
        name=DIRECTED_ACTIONS[5*45000+44]
        first=execute_authoring(base,name,arguments(name))
        second=execute_authoring(base,name,arguments(name))
        self.assertEqual(project_digest(first),project_digest(second))
        self.assertEqual(project_digest(base),project_digest(original_project()))
        with self.assertRaises(StudioError):
            apply_authoring_batch(base,[
                {"action":name,"parameters":arguments(name)},
                {"action":name,"parameters":{
                    **arguments(name),"instance_id":"../../escape",
                }},
            ])
        self.assertEqual(project_digest(base),project_digest(original_project()))

    def test_same_composition_can_author_two_independent_longform_chapters(self):
        base=original_project()
        name=DIRECTED_ACTIONS[8*45000+9]
        a=execute_authoring(base,name,{
            **arguments(name),"instance_id":"chapterA"})
        b=execute_authoring(a,name,{
            **arguments(name),"instance_id":"chapterB"})
        self.assertEqual(len(base.native_quests)+2,len(b.native_quests))
        self.assertEqual(len(base.placements)+8,len(b.placements))
        self.assertEqual(project_digest(b),project_digest(
            load_authored_document(authored_document(b),project_id=base.project_id)))
        with self.assertRaises(StudioError):
            execute_authoring(a,name,{
                **arguments(name),"instance_id":"chapterA"})

    def test_summary_never_serializes_half_million_names(self):
        summary=authored_summary(original_project())
        self.assertEqual(500,len(summary["action_catalog"]))
        self.assertEqual(4500,summary["classic_recipe_count"])
        self.assertEqual(45000,summary["expanded_recipe_count"])
        self.assertEqual(450000,summary["directed_recipe_count"])
        self.assertEqual(4999500,summary["recipe_catalog_count"])
        self.assertEqual(5000000,summary["catalog_total"])

    def test_native_godot_exports_directed_source_content(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        base=original_project()
        name=DIRECTED_ACTIONS[5*45000+3]
        edited=execute_authoring(base,name,arguments(name))
        generated=compile_studio_expedition(
            edited,ArchipelagoProfile(
                seed=73,islands=4,caverns=0,
                include_portals=False,include_underwater=False),
            playtest_routes=2,include_godot=True)
        self.assertIn("game/frontier/studio_terrain.json",
                      generated["godot_project_files"])
        self.assertIn("game/frontier/studio_terrain.gd",
                      generated["godot_project_files"])
        self.assertGreater(generated["travel_edges"],0)


if __name__=="__main__":
    unittest.main()
