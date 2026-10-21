"""Fifty-million original game-production acceptance and handbook proofs.

Proves virtual exact 45M plan indexing, source-changing gameplay compositions,
native game event/quest/actor semantics and 9,000 generated, exportable
technical handbooks. Do not allocate all 50M registered strings in tests.
"""
from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
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
from skeleton.forge.game_frontier_studio_worldline_production import (
    WORLDLINE_ACTIONS, WORLDLINES, WORLDLINE_EFFECTS,
    describe_worldline, search_worldlines,
)
from skeleton.forge.game_frontier_studio_final_production import (
    FINAL_PRODUCTION_ACTIONS,
)
from skeleton.forge.game_frontier_studio_worldline_handbooks import (
    VOLUME_COUNT, HANDBOOK_PATHS, identity, volume_number,
    list_volumes, render_handbook, handbook_receipt,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project, arguments,
)


class FiftyMillionAuthoringAcceptance(unittest.TestCase):
    def test_virtual_catalog_uses_stable_source_indices(self):
        self.assertGreaterEqual(len(AUTHORING_ACTIONS),50_000_000)
        self.assertEqual(45_000_000,len(WORLDLINE_ACTIONS))
        self.assertEqual(WORLDLINE_ACTIONS[0],AUTHORING_ACTIONS[5_000_000])
        self.assertEqual(WORLDLINE_ACTIONS[-1],AUTHORING_ACTIONS[49_999_999])
        self.assertEqual(WORLDLINE_ACTIONS[:12],
                         AUTHORING_ACTIONS[5_000_000:5_000_012])
        self.assertIn(WORLDLINE_ACTIONS[-1],AUTHORING_ACTIONS)
        self.assertNotIn("worldline_exec_os_code______river_network",
                         AUTHORING_ACTIONS)
        with self.assertRaises(IndexError):
            _=WORLDLINE_ACTIONS[45_000_000]

    def test_all_ten_worldlines_resolve_source_owned_parent_index(self):
        for parent in (0,1,9,10,449,450,899,900,4500,45000,
                       450000,999999,2249999,4499999):
            for axis in range(10):
                name=WORLDLINE_ACTIONS[parent*10+axis]
                source=FINAL_PRODUCTION_ACTIONS[parent]
                self.assertEqual(
                    "worldline_"+source.removeprefix("complete_")+
                    "______"+WORLDLINES[axis],name)
                self.assertIn(name,WORLDLINE_ACTIONS)
                info=describe_worldline(name)
                self.assertEqual(source,info["base_operation"])
                self.assertEqual(WORLDLINES[axis],info["worldline"])
                self.assertTrue(info["actual_project_mutation"])

    def test_each_domain_and_worldline_executes_real_game_source(self):
        source=original_project()
        before=project_digest(source)
        for domain in range(10):
            outputs=set()
            for axis in range(10):
                name=WORLDLINE_ACTIONS[domain*4_500_000+axis]
                with self.subTest(domain=domain,worldline=WORLDLINES[axis]):
                    changed=execute_authoring(source,name,arguments(name))
                    self.assertIsInstance(changed,StudioProject)
                    self.assertNotEqual(before,project_digest(changed))
                    self.assertGreater(len(changed.environmental_pages),
                                       len(source.environmental_pages))
                    outputs.add(project_digest(changed))
            self.assertEqual(10,len(outputs))
        self.assertEqual(before,project_digest(source))

    def test_real_worldline_event_uses_observed_water_signals(self):
        source=original_project()
        made=execute_authoring(source,WORLDLINE_ACTIONS[0],
                                arguments(WORLDLINE_ACTIONS[0]))
        page=made.environmental_pages[-1]
        self.assertEqual("inspect_instrument",page.actions[0].kind)
        self.assertEqual({"tide_height_m","water_depth_m"},
                         {x.signal for x in page.conditions})
        accepted=evaluate_environment_events(
            (page,),current={"tide_height_m":2.,"water_depth_m":1.},
            now_ms=5000)
        self.assertEqual(1,len(accepted.accepted))
        self.assertTrue(accepted.required_runtime_approvals)
        blocked=evaluate_environment_events(
            (page,),current={"tide_height_m":0.,"water_depth_m":0.},
            now_ms=5000)
        self.assertEqual(0,len(blocked.accepted))

    def test_actor_and_quest_continuity_only_refine_new_source(self):
        original=original_project()
        actor_name=WORLDLINE_ACTIONS[2*4_500_000+5]
        actor_game=execute_authoring(original,actor_name,arguments(actor_name))
        self.assertEqual(original.placements,
                         actor_game.placements[:len(original.placements)])
        self.assertEqual(len(original.placements)+4,
                         len(actor_game.placements))
        quest_name=WORLDLINE_ACTIONS[3*4_500_000+9]
        story_game=execute_authoring(original,quest_name,arguments(quest_name))
        q=story_game.native_quests[-1]
        new=[stage for stage in q.stages if "_wl_" in stage.stage_id]
        self.assertEqual(1,len(new))
        self.assertIn(new[0].stage_id,q.stages[0].next_stage_ids)
        self.assertTrue(compile_studio_native_quest_graph(story_game)["quests"])

    def test_paginated_45m_search_matches_virtual_index(self):
        for offset in (0,31,450,45_000,1_000_000,44_999_990):
            with self.subTest(offset=offset):
                page=search_worldlines(offset=offset,limit=32)
                expected=WORLDLINE_ACTIONS[
                    offset:min(offset+32,45_000_000)]
                self.assertEqual(expected,
                                 tuple(x["operation"] for x in page["items"]))
        selected=search_worldlines(domain="stronghold",
             director="audio_cues",worldline="sky_navigation",
             system_layer="stealth",finish="alternate_endings",
             offset=10,limit=7)
        self.assertEqual(450,selected["matched"])
        self.assertEqual(7,len(selected["items"]))
        self.assertTrue(all(x["worldline"]=="sky_navigation" for x in selected["items"]))
        with self.assertRaises(StudioError):
            search_worldlines(limit=65)
        with self.assertRaises(StudioError):
            search_worldlines(query="quest")
        with self.assertRaises(StudioError):
            search_worldlines(worldline="../escape")

    def test_worldline_chapter_instances_roundtrip_and_roll_back(self):
        original=original_project()
        first_name=WORLDLINE_ACTIONS[8*4_500_000+8]
        a=execute_authoring(original,first_name,
            {**arguments(first_name),"instance_id":"chapterA"})
        b=execute_authoring(a,first_name,
            {**arguments(first_name),"instance_id":"chapterB"})
        self.assertEqual(len(original.native_quests)+2,len(b.native_quests))
        recovered=load_authored_document(authored_document(b),
                                         project_id=original.project_id)
        self.assertEqual(project_digest(b),project_digest(recovered))
        with self.assertRaises(StudioError):
            execute_authoring(a,first_name,{
                **arguments(first_name),"instance_id":"chapterA"})
        with self.assertRaises(StudioError):
            apply_authoring_batch(original,[
                {"action":first_name,"parameters":arguments(first_name)},
                {"action":first_name,"parameters":{
                    **arguments(first_name),"instance_id":"../../bad"}},
            ])
        self.assertEqual(project_digest(original),project_digest(original_project()))

    def test_export_native_game_source_from_worldline(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        original=original_project()
        name=WORLDLINE_ACTIONS[5*4_500_000+3]
        authored=execute_authoring(original,name,arguments(name))
        game=compile_studio_expedition(
            authored,ArchipelagoProfile(
                seed=53,islands=4,caverns=0,
                include_portals=False,include_underwater=False),
            include_godot=True,playtest_routes=2)
        self.assertIn("game/frontier/studio_terrain.gd",game["godot_project_files"])
        self.assertIn("game/frontier/studio_terrain.json",game["godot_project_files"])
        self.assertGreater(game["travel_edges"],0)

    def test_project_summary_is_bounded_and_total_is_50m(self):
        s=authored_summary(original_project())
        self.assertEqual(500,len(s["action_catalog"]))
        self.assertEqual(45_000_000,s["worldline_recipe_count"])
        self.assertEqual(499_999_999_500,s["recipe_catalog_count"])
        self.assertEqual(500_000_000_000,s["catalog_total"])


class NineThousandHandbooks(unittest.TestCase):
    def test_every_volume_has_unique_reversible_ownership(self):
        self.assertEqual(9000,VOLUME_COUNT)
        self.assertEqual(9000,len(HANDBOOK_PATHS))
        seen=set()
        for i in range(9000):
            owner=identity(i)
            self.assertEqual(i,volume_number(*owner))
            seen.add(HANDBOOK_PATHS[i])
        self.assertEqual(9000,len(seen))
        self.assertEqual("game_studio_50000000/realm/waterways/navigation_alternates/river_network.md",
                         HANDBOOK_PATHS[0])

    def test_volume_page_filters_are_bounded_and_stable(self):
        first=list_volumes(domain="living_story",worldline="cinematic_blocking",
                           offset=0,limit=8)
        second=list_volumes(domain="living_story",worldline="cinematic_blocking",
                            offset=8,limit=8)
        self.assertEqual(90,first["matched"])
        self.assertFalse({x["path"] for x in first["items"]} &
                         {x["path"] for x in second["items"]})
        with self.assertRaises(StudioError):
            list_volumes(limit=65)

    def test_ten_source_verified_manuals_are_distinct_markdown(self):
        docs=[]
        for axis in range(10):
            d,t,r,l=identity(axis)
            result=handbook_receipt(d,t,r,l)
            self.assertIn("Fifty source-backed",result["markdown"])
            self.assertIn("Thirty adversarial",result["markdown"])
            self.assertEqual(result["covered_commands"],5000)
            self.assertEqual(len(result["content_sha256"]),64)
            docs.append(result["content_sha256"])
        self.assertEqual(10,len(set(docs)))

    def test_handbook_export_generates_real_files_with_hash_receipts(self):
        from scripts.export_game_studio_worldline_handbooks import export
        with TemporaryDirectory() as temp:
            receipt=export(Path(temp),offset=0,limit=2)
            self.assertEqual(2,receipt["exported"])
            self.assertTrue(Path(receipt["manifest"]).exists())
            self.assertTrue((Path(temp)/HANDBOOK_PATHS[0]).exists())
            self.assertIn("original",render_handbook(*identity(0)).lower())


if __name__=="__main__":
    unittest.main()
