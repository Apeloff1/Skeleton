"""Five-million-operation Forge Studio functional qualification.

Validate the 4.5M *virtual* source-authored finishing contracts, 100 concrete
domain/pass executions, project roundtrips, typed gameplay sensors, stable
chapter replay, original cast and quest preservation and native Godot output.
Do not confuse composite operations with independent pretrained engines.
"""
from __future__ import annotations
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioProject, compile_studio_native_quest_graph,
    compile_studio_expedition,
)
from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, authored_summary, execute_authoring,
    apply_authoring_batch, project_digest,
)
from skeleton.forge.game_frontier_studio_final_production import (
    FINAL_PRODUCTION_ACTIONS, FINISHES, FINISH_EFFECTS,
    describe_final_action, search_final_actions,
)
from skeleton.forge.game_frontier_studio_directed_production import (
    DIRECTED_ACTIONS,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project, arguments,
)


class FiveMillionProductionAcceptance(unittest.TestCase):
    def test_five_million_registered_without_eager_strings(self):
        self.assertEqual(5_000_000,len(AUTHORING_ACTIONS))
        self.assertEqual(4_500_000,len(FINAL_PRODUCTION_ACTIONS))
        self.assertEqual(10,len(FINISHES))
        self.assertEqual(10,len(FINISH_EFFECTS))
        self.assertEqual(FINAL_PRODUCTION_ACTIONS[0],AUTHORING_ACTIONS[500_000])
        self.assertEqual(FINAL_PRODUCTION_ACTIONS[-1],AUTHORING_ACTIONS[-1])
        self.assertEqual(FINAL_PRODUCTION_ACTIONS[:30],
                         AUTHORING_ACTIONS[500_000:500_030])
        self.assertTrue(FINAL_PRODUCTION_ACTIONS[-1] in AUTHORING_ACTIONS)
        self.assertNotIn("complete_eval_python_____route_optimization",
                         FINAL_PRODUCTION_ACTIONS)
        with self.assertRaises(IndexError):
            _=FINAL_PRODUCTION_ACTIONS[4_500_000]

    def test_all_source_director_and_finish_indices_are_reversible(self):
        # Arithmetic specification is checked at every domain, 50 archetype
        # identities, nine styles, ten layers, ten directors and ten finishes,
        # without allocating a 4.5M item set in CI.
        for base in (0,1,9,10,99,899,900,4499,4500,44999,
                     45000,99999,224999,449999):
            for finish in range(10):
                position=base*10+finish
                name=FINAL_PRODUCTION_ACTIONS[position]
                owner=DIRECTED_ACTIONS[base]
                self.assertEqual(
                    "complete_"+owner.removeprefix("direct_")+"_____"+
                    FINISHES[finish],name)
                self.assertIn(name,FINAL_PRODUCTION_ACTIONS)
                description=describe_final_action(name)
                self.assertEqual(owner,description["base_operation"])
                self.assertEqual(FINISHES[finish],description["finish"])
                self.assertTrue(description["actual_project_mutation"])

    def test_each_of_ten_finishes_really_changes_game_for_ten_domains(self):
        base=original_project()
        original_hash=project_digest(base)
        for domain in range(10):
            outcomes=set()
            for finish in range(10):
                # Each domain covers 450 parent recipes, 10 game layers,
                # 10 directors, then ten finishing-pass variants.
                action=FINAL_PRODUCTION_ACTIONS[domain*450000+finish]
                with self.subTest(domain=domain,pass_name=FINISHES[finish]):
                    made=execute_authoring(base,action,arguments(action))
                    self.assertIsInstance(made,StudioProject)
                    self.assertNotEqual(original_hash,project_digest(made))
                    self.assertGreater(len(made.environmental_pages),
                                       len(base.environmental_pages))
                    outcomes.add(project_digest(made))
            self.assertEqual(10,len(outcomes))
        self.assertEqual(original_hash,project_digest(base))

    def test_each_original_archetype_is_covered_by_a_composable_finisher(self):
        original=original_project()
        digest=project_digest(original)
        for domain in range(10):
            for archetype in range(50):
                action=FINAL_PRODUCTION_ACTIONS[
                    domain*450000+archetype*9000]
                with self.subTest(operation=action):
                    output=execute_authoring(original,action,arguments(action))
                    self.assertNotEqual(digest,project_digest(output))
                    self.assertGreater(len(output.environmental_pages),
                                       len(original.environmental_pages))

    def test_finisher_evaluates_observed_navigation_readings(self):
        base=original_project()
        action=FINAL_PRODUCTION_ACTIONS[0]
        made=execute_authoring(base,action,arguments(action))
        page=made.environmental_pages[-1]
        self.assertEqual(2,len(page.conditions))
        self.assertEqual("inspect_instrument",page.actions[0].kind)
        valid=evaluate_environment_events(
            (page,),current={"compass_heading_deg":135,
                             "fog_visibility_m":110},now_ms=10000)
        self.assertEqual(1,len(valid.accepted))
        self.assertTrue(valid.required_runtime_approvals)
        invalid=evaluate_environment_events(
            (page,),current={"compass_heading_deg":10,
                             "fog_visibility_m":900},now_ms=10000)
        self.assertEqual(0,len(invalid.accepted))

    def test_actor_interactions_preserve_original_ids(self):
        original=original_project()
        name=FINAL_PRODUCTION_ACTIONS[2*450000+7]
        completed=execute_authoring(original,name,arguments(name))
        self.assertEqual(original.placements,
                         completed.placements[:len(original.placements)])
        self.assertEqual(len(original.placements)+4,
                         len(completed.placements))
        self.assertEqual(len(original.events)+4,len(completed.events))
        targets={e.target for e in completed.events[len(original.events):]}
        self.assertEqual(4,len(targets))

    def test_new_quest_gets_reachable_alternative_and_canon_preserved(self):
        original=original_project()
        name=FINAL_PRODUCTION_ACTIONS[3*450000+9]
        output=execute_authoring(original,name,arguments(name))
        quest=output.native_quests[-1]
        stages=[s for s in quest.stages if "_fin_" in s.stage_id]
        self.assertEqual(1,len(stages))
        self.assertIn(stages[0].stage_id,quest.stages[0].next_stage_ids)
        self.assertEqual(1,len(stages[0].next_stage_ids))
        graph=compile_studio_native_quest_graph(output)
        self.assertGreater(len(graph["quests"]),len(original.native_quests))

    def test_arithmetic_page_order_and_filtered_page_size(self):
        for offset in (0,1,31,4500,499999,1000000,4499968,4499999):
            with self.subTest(offset=offset):
                output=search_final_actions(offset=offset,limit=32)
                expected=FINAL_PRODUCTION_ACTIONS[
                    offset:min(4_500_000,offset+32)]
                self.assertEqual(
                    expected,tuple(item["operation"] for item in output["items"]))
                self.assertEqual(4_500_000,output["matched"])
        filtered=search_final_actions(
            domain="expedition",system_layer="stealth",
            director="audio_cues",finish="vertical_routes",
            offset=14,limit=7)
        self.assertEqual(450,filtered["matched"])
        self.assertEqual(7,len(filtered["items"]))
        self.assertTrue(all(
            item["finish"]=="vertical_routes" for item in filtered["items"]))
        with self.assertRaises(StudioError):
            search_final_actions(finish="run_os_shell")
        with self.assertRaises(StudioError):
            search_final_actions(limit=65)

    def test_batch_immutable_rollback_and_repeatable_chapter_instances(self):
        original=original_project()
        before=project_digest(original)
        name=FINAL_PRODUCTION_ACTIONS[8*450000+8]
        first=execute_authoring(original,name,{
            **arguments(name),"instance_id":"volumeA"})
        second=execute_authoring(first,name,{
            **arguments(name),"instance_id":"volumeB"})
        self.assertEqual(len(original.native_quests)+2,
                         len(second.native_quests))
        self.assertEqual(len(original.placements)+8,
                         len(second.placements))
        recovered=load_authored_document(
            authored_document(second),project_id=original.project_id)
        self.assertEqual(project_digest(second),project_digest(recovered))
        with self.assertRaises(StudioError):
            execute_authoring(first,name,{
                **arguments(name),"instance_id":"volumeA"})
        with self.assertRaises(StudioError):
            apply_authoring_batch(original,[
                {"action":name,"parameters":arguments(name)},
                {"action":name,"parameters":{
                    **arguments(name),"instance_id":"../../escape"}},
            ])
        self.assertEqual(before,project_digest(original))

    def test_summary_is_bounded_and_source_counts_are_correct(self):
        summary=authored_summary(original_project())
        self.assertEqual(500,len(summary["action_catalog"]))
        self.assertEqual(4500,summary["classic_recipe_count"])
        self.assertEqual(45000,summary["expanded_recipe_count"])
        self.assertEqual(450000,summary["directed_recipe_count"])
        self.assertEqual(4500000,summary["final_recipe_count"])
        self.assertEqual(4999500,summary["recipe_catalog_count"])
        self.assertEqual(5000000,summary["catalog_total"])

    def test_native_godot_compiles_final_authored_source(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        base=original_project()
        name=FINAL_PRODUCTION_ACTIONS[5*450000+3]
        output=execute_authoring(base,name,arguments(name))
        game=compile_studio_expedition(
            output,ArchipelagoProfile(
                seed=47,islands=4,caverns=0,
                include_portals=False,include_underwater=False),
            include_godot=True,playtest_routes=2)
        self.assertIn("game/frontier/studio_terrain.gd",
                      game["godot_project_files"])
        self.assertIn("game/frontier/studio_terrain.json",
                      game["godot_project_files"])
        self.assertGreater(game["travel_edges"],0)


if __name__=="__main__":
    unittest.main()
