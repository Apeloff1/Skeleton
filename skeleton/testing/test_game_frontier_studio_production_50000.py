"""Functional qualification for 45,000 composed cross-system game operations.

This suite distinguishes registered source-changing recipes from individually
written engines. Every gameplay layer is exercised through the real canonical
immutable StudioProject, native events and expedition export, plus the 45k
plan registry, source roundtrip, CAS-friendly atomic batches and search.
"""
from __future__ import annotations

import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioProject, compile_studio_expedition,
    compile_studio_native_quest_graph,
)
from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, apply_authoring_batch,
    authored_summary, execute_authoring, project_digest,
)
from skeleton.forge.game_frontier_studio_system_expansions import (
    EXPANDED_RECIPE_ACTIONS, EXPANDED_RECIPE_INDEX, GAMEPLAY_LAYERS,
    describe_expansion, search_expansions,
)
from skeleton.forge.game_frontier_studio_production_recipes import RECIPE_ACTIONS
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project, arguments,
)


class FiftyThousandProductionOperations(unittest.TestCase):
    def test_full_50000_registry_is_distinct_and_generation_stable(self):
        self.assertGreaterEqual(len(AUTHORING_ACTIONS), 50000)
        self.assertEqual(len(AUTHORING_ACTIONS[:500]), len(set(AUTHORING_ACTIONS[:500])))
        self.assertEqual(45000, len(EXPANDED_RECIPE_ACTIONS))
        self.assertEqual(45000, len(EXPANDED_RECIPE_INDEX))
        self.assertEqual(EXPANDED_RECIPE_ACTIONS, AUTHORING_ACTIONS[5000:50000])

    def test_45000_unique_plans_are_typed_game_production_compositions(self):
        seen=set()
        by_system={system:0 for system in GAMEPLAY_LAYERS}
        by_domain={}
        for name in EXPANDED_RECIPE_ACTIONS:
            meta=describe_expansion(name)
            index=EXPANDED_RECIPE_INDEX[name]
            base_index, system_index=divmod(index,10)
            self.assertEqual(RECIPE_ACTIONS[base_index],meta["base_operation"])
            self.assertEqual(GAMEPLAY_LAYERS[system_index],meta["system_layer"])
            self.assertTrue(meta["actual_project_mutation"])
            self.assertIn("map_tiles",meta["cross_system_source_edits"])
            self.assertIn("environmental_page",meta["cross_system_source_edits"])
            key=(meta["base_operation"],meta["system_layer"])
            self.assertNotIn(key,seen)
            seen.add(key)
            by_system[meta["system_layer"]]+=1
            by_domain[meta["domain"]]=by_domain.get(meta["domain"],0)+1
        self.assertEqual(45000,len(seen))
        self.assertTrue(all(n==4500 for n in by_system.values()))
        self.assertEqual(10,len(by_domain))
        self.assertTrue(all(n==4500 for n in by_domain.values()))

    def test_ten_gameplay_layers_mutate_real_source_in_all_ten_domains(self):
        base=original_project()
        digest=project_digest(base)
        for domain in range(10):
            distinct=set()
            for layer in range(10):
                recipe=EXPANDED_RECIPE_ACTIONS[domain*4500+layer]
                with self.subTest(domain=domain,layer=GAMEPLAY_LAYERS[layer]):
                    changed=execute_authoring(base,recipe,arguments(recipe))
                    self.assertIsInstance(changed,StudioProject)
                    self.assertNotEqual(digest,project_digest(changed))
                    self.assertEqual(len(base.environmental_pages)+
                                     (2 if domain in (4,9) else 1),
                                     len(changed.environmental_pages))
                    distinct.add(project_digest(changed))
            self.assertEqual(10,len(distinct))
        self.assertEqual(digest,project_digest(base))

    def test_fifty_blueprints_per_domain_keep_real_game_edits(self):
        original=original_project()
        before=project_digest(original)
        for domain in range(10):
            for source in range(50):
                index=domain*4500+source*90+9
                recipe=EXPANDED_RECIPE_ACTIONS[index]
                with self.subTest(recipe=recipe):
                    updated=execute_authoring(original,recipe,arguments(recipe))
                    self.assertNotEqual(before,project_digest(updated))
                    self.assertGreater(len(updated.environmental_pages),
                                       len(original.environmental_pages))
        self.assertEqual(before,project_digest(original))

    def test_real_environmental_page_proposes_action_from_observed_values(self):
        base=original_project()
        recipe=EXPANDED_RECIPE_ACTIONS[0]
        output=execute_authoring(base,recipe,arguments(recipe))
        page=output.environmental_pages[-1]
        self.assertEqual("inspect_instrument",page.actions[0].kind)
        accepted=evaluate_environment_events(
            (page,),current={"compass_heading_deg":180,"fog_visibility_m":100},
            now_ms=10000)
        self.assertEqual(1,len(accepted.accepted))
        self.assertTrue(accepted.required_runtime_approvals)
        denied=evaluate_environment_events(
            (page,),current={"compass_heading_deg":10,"fog_visibility_m":500},
            now_ms=10000)
        self.assertEqual(0,len(denied.accepted))

    def test_expanded_quests_have_real_reachable_gameplay_branches(self):
        base=original_project()
        recipe=EXPANDED_RECIPE_ACTIONS[3*4500+9]
        next_project=execute_authoring(base,recipe,arguments(recipe))
        quest=next_project.native_quests[-1]
        self.assertGreater(len(quest.stages),6)
        new=[x for x in quest.stages if "_gameplay_" in x.stage_id]
        self.assertEqual(1,len(new))
        self.assertEqual(1,len(new[0].next_stage_ids))
        native=compile_studio_native_quest_graph(next_project)
        self.assertGreaterEqual(len(native["quests"]),1)

    def test_expanded_encounters_change_only_new_cast_and_keep_interactions(self):
        base=original_project()
        recipe=EXPANDED_RECIPE_ACTIONS[2*4500+7]
        result=execute_authoring(base,recipe,arguments(recipe))
        self.assertEqual(base.placements,result.placements[:len(base.placements)])
        self.assertEqual(len(base.placements)+4,len(result.placements))
        self.assertEqual(len(base.events)+4,len(result.events))
        actors=result.placements[len(base.placements):]
        self.assertTrue(any(actor.z>0 for actor in actors))
        self.assertEqual(4,len({
            event.target for event in result.events[len(base.events):]
        }))

    def test_search_45k_is_stable_bounded_and_filters_actual_game_system(self):
        a=search_expansions(query="sky",domain="wildland",limit=7)
        b=search_expansions(query="sky",domain="wildland",offset=7,limit=7)
        self.assertEqual(45000,a["total_catalog"])
        self.assertEqual(7,len(a["items"]))
        self.assertFalse({item["operation"] for item in a["items"]} &
                         {item["operation"] for item in b["items"]})
        focused=search_expansions(domain="expedition",system_layer="combat",
                                 limit=16)
        self.assertEqual(450,focused["matched"])
        self.assertEqual("combat",focused["items"][0]["system_layer"])
        with self.assertRaises(StudioError):
            search_expansions(limit=1000)
        with self.assertRaises(StudioError):
            search_expansions(system_layer="../../file")

    def test_two_stable_instances_preserve_immutable_source_and_roundtrip(self):
        original=original_project()
        recipe=EXPANDED_RECIPE_ACTIONS[8*4500+8]
        first=execute_authoring(original,recipe,{
            **arguments(recipe),"instance_id":"partA"})
        second=execute_authoring(first,recipe,{
            **arguments(recipe),"instance_id":"partB"})
        self.assertEqual(len(original.native_quests)+2,len(second.native_quests))
        self.assertEqual(len(original.placements)+8,len(second.placements))
        self.assertEqual(project_digest(second),project_digest(
            load_authored_document(authored_document(second),
                                   project_id=original.project_id)))
        with self.assertRaises(StudioError):
            execute_authoring(first,recipe,{
                **arguments(recipe),"instance_id":"partA"})
        self.assertEqual(project_digest(original),project_digest(original_project()))

    def test_expanded_recipe_batch_fails_atomically_on_untrusted_source(self):
        original=original_project()
        digest=project_digest(original)
        action=EXPANDED_RECIPE_ACTIONS[4*4500+2]
        with self.assertRaises(StudioError):
            apply_authoring_batch(original,[
                {"action":action,"parameters":arguments(action)},
                {"action":action,"parameters":{
                    **arguments(action),"instance_id":"../../unsafe"}},
            ])
        self.assertEqual(digest,project_digest(original))

    def test_summary_is_bounded_even_with_50000_executable_commands(self):
        data=authored_summary(original_project())
        self.assertEqual(500,len(data["action_catalog"]))
        self.assertEqual(4500,data["classic_recipe_count"])
        self.assertEqual(45000,data["expanded_recipe_count"])
        self.assertEqual(4999999500,data["recipe_catalog_count"])
        self.assertEqual(5000000000,data["catalog_total"])

    def test_native_game_export_consumes_expanded_terrain_and_event_source(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        base=original_project()
        recipe=EXPANDED_RECIPE_ACTIONS[5*4500+8]
        completed=execute_authoring(base,recipe,arguments(recipe))
        game=compile_studio_expedition(
            completed,ArchipelagoProfile(seed=51,islands=4,caverns=0,
                                         include_portals=False,include_underwater=False),
            playtest_routes=2,include_godot=True,
        )
        self.assertIn("game/frontier/studio_terrain.json",
                      game["godot_project_files"])
        self.assertIn("game/frontier/studio_terrain.gd",
                      game["godot_project_files"])
        self.assertGreater(game["travel_edges"],0)
        self.assertGreater(len(completed.environmental_pages),0)


if __name__=="__main__":
    unittest.main()
