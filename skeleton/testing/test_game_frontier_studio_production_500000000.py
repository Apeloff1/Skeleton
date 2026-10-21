"""500M exact source-authoring plans and 90K real handbook contracts.

Covers virtual rank/unrank, gameplay event pages, story/cast source integrity,
native Godot export, authenticated API-ready handbook bounds and actual
materialization with SHA receipts. Not a claim of 500M finished games.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError,StudioProject,compile_studio_native_quest_graph,
    compile_studio_expedition,
)
from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS,authored_summary,execute_authoring,
    apply_authoring_batch,project_digest,
)
from skeleton.forge.game_frontier_studio_phase_production import (
    PHASE_ACTIONS,PHASES,PHASE_EFFECTS,describe_phase,search_phases,
)
from skeleton.forge.game_frontier_studio_worldline_production import WORLDLINE_ACTIONS
from skeleton.forge.game_frontier_studio_phase_handbooks import (
    BOOK_COUNT,PHASE_BOOK_PATHS,number,identity,list_books,receipt,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document,load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project,arguments,
)


class FiveHundredMillionGameProduction(unittest.TestCase):
    def test_500m_registry_is_virtual_and_stable(self):
        self.assertEqual(500_000_000,len(AUTHORING_ACTIONS))
        self.assertEqual(450_000_000,len(PHASE_ACTIONS))
        self.assertEqual(AUTHORING_ACTIONS[50_000_000],PHASE_ACTIONS[0])
        self.assertEqual(AUTHORING_ACTIONS[-1],PHASE_ACTIONS[-1])
        self.assertEqual(PHASE_ACTIONS[:24],AUTHORING_ACTIONS[50_000_000:50_000_024])
        self.assertTrue(PHASE_ACTIONS[-1] in AUTHORING_ACTIONS)
        self.assertNotIn("phase_execute_arbitrary_code_______dawn_routes",AUTHORING_ACTIONS)
        with self.assertRaises(IndexError):
            _=PHASE_ACTIONS[450_000_000]

    def test_all_ten_phases_resolve_exact_source_parent(self):
        for i in (0,1,9,10,49,100,4499,450000,4_500_000,22_499_999,44_999_999):
            for p in range(10):
                name=PHASE_ACTIONS[i*10+p]
                source=WORLDLINE_ACTIONS[i]
                self.assertEqual(
                    "phase_"+source.removeprefix("worldline_")+"_______"+PHASES[p],name)
                self.assertIn(name,PHASE_ACTIONS)
                spec=describe_phase(name)
                self.assertEqual(source,spec["base_operation"])
                self.assertEqual(PHASES[p],spec["phase"])
                self.assertTrue(spec["actual_project_mutation"])

    def test_ten_production_domains_and_ten_phase_systems_edit_real_source(self):
        base=original_project()
        before=project_digest(base)
        for domain in range(10):
            outputs=set()
            for phase in range(10):
                name=PHASE_ACTIONS[domain*45_000_000+phase]
                with self.subTest(domain=domain,phase=PHASES[phase]):
                    candidate=execute_authoring(base,name,arguments(name))
                    self.assertIsInstance(candidate,StudioProject)
                    self.assertNotEqual(before,project_digest(candidate))
                    self.assertGreater(len(candidate.environmental_pages),
                                       len(base.environmental_pages))
                    outputs.add(project_digest(candidate))
            self.assertEqual(10,len(outputs))
        self.assertEqual(before,project_digest(base))

    def test_event_page_requires_real_game_sensors(self):
        base=original_project()
        page=execute_authoring(base,PHASE_ACTIONS[0],
                  arguments(PHASE_ACTIONS[0])).environmental_pages[-1]
        self.assertEqual("inspect_instrument",page.actions[0].kind)
        self.assertEqual({"solar_height","fog_visibility_m"},
                         {x.signal for x in page.conditions})
        accepted=evaluate_environment_events(
            (page,),current={"solar_height":25,"fog_visibility_m":100},
            now_ms=10_000)
        self.assertEqual(1,len(accepted.accepted))
        self.assertTrue(accepted.required_runtime_approvals)
        suppressed=evaluate_environment_events(
            (page,),current={"solar_height":-5,"fog_visibility_m":900},
            now_ms=10_000)
        self.assertEqual(0,len(suppressed.accepted))

    def test_production_scene_retains_cast_and_quest_canon(self):
        base=original_project()
        p=execute_authoring(base,PHASE_ACTIONS[2*45_000_000+7],
                            arguments(PHASE_ACTIONS[2*45_000_000+7]))
        self.assertEqual(base.placements,p.placements[:len(base.placements)])
        self.assertEqual(len(base.placements)+4,len(p.placements))
        q=execute_authoring(base,PHASE_ACTIONS[3*45_000_000+9],
                            arguments(PHASE_ACTIONS[3*45_000_000+9]))
        quest=q.native_quests[-1]
        branches=[s for s in quest.stages if "_ph_" in s.stage_id]
        self.assertEqual(1,len(branches))
        self.assertIn(branches[0].stage_id,quest.stages[0].next_stage_ids)
        self.assertTrue(compile_studio_native_quest_graph(q)["quests"])

    def test_arithmetic_search_order_at_boundaries_and_filters(self):
        for offset in (0,1,31,54_321,12_345_678,449_999_975):
            with self.subTest(offset=offset):
                page=search_phases(offset=offset,limit=32)
                self.assertEqual(
                    PHASE_ACTIONS[offset:min(offset+32,450_000_000)],
                    tuple(x["operation"] for x in page["items"]))
                self.assertEqual(450_000_000,page["matched"])
        filtered=search_phases(domain="expedition",system_layer="stealth",
          director="audio_cues",finish="alternate_endings",
          worldline="sky_navigation",phase="storm_shelters",offset=6,limit=8)
        self.assertEqual(450,filtered["matched"])
        self.assertEqual(8,len(filtered["items"]))
        with self.assertRaises(StudioError):
            search_phases(limit=100)
        with self.assertRaises(StudioError):
            search_phases(query="quest")
        with self.assertRaises(StudioError):
            search_phases(phase="../../outside")

    def test_repeatable_chapters_and_atomic_rejection(self):
        base=original_project()
        name=PHASE_ACTIONS[8*45_000_000+8]
        a=execute_authoring(base,name,{**arguments(name),"instance_id":"partA"})
        b=execute_authoring(a,name,{**arguments(name),"instance_id":"partB"})
        self.assertEqual(len(base.native_quests)+2,len(b.native_quests))
        self.assertEqual(project_digest(b),project_digest(
            load_authored_document(authored_document(b),project_id=base.project_id)))
        with self.assertRaises(StudioError):
            execute_authoring(a,name,{**arguments(name),"instance_id":"partA"})
        with self.assertRaises(StudioError):
            apply_authoring_batch(base,[
                {"action":name,"parameters":arguments(name)},
                {"action":name,"parameters":{
                    **arguments(name),"instance_id":"../../escape"}},
            ])
        self.assertEqual(project_digest(base),project_digest(original_project()))

    def test_native_godot_world_uses_phase_content(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        base=original_project()
        name=PHASE_ACTIONS[5*45_000_000+3]
        edited=execute_authoring(base,name,arguments(name))
        output=compile_studio_expedition(
            edited,ArchipelagoProfile(seed=77,islands=4,caverns=0,
                                      include_portals=False,include_underwater=False),
            include_godot=True,playtest_routes=2)
        self.assertIn("game/frontier/studio_terrain.json",output["godot_project_files"])
        self.assertIn("game/frontier/studio_terrain.gd",output["godot_project_files"])
        self.assertGreater(output["travel_edges"],0)

    def test_bounded_summary_reports_exact_counts(self):
        meta=authored_summary(original_project())
        self.assertEqual(500,len(meta["action_catalog"]))
        self.assertEqual(450_000_000,meta["phase_recipe_count"])
        self.assertEqual(499_999_500,meta["recipe_catalog_count"])
        self.assertEqual(500_000_000,meta["catalog_total"])


class NinetyThousandGameHandbooks(unittest.TestCase):
    def test_90000_exact_volume_indices_and_path_uniqueness(self):
        self.assertEqual(90_000,BOOK_COUNT)
        seen=set()
        for k in range(BOOK_COUNT):
            args=identity(k)
            self.assertEqual(k,number(*args))
            seen.add(PHASE_BOOK_PATHS[k])
        self.assertEqual(BOOK_COUNT,len(seen))
        self.assertEqual("game_studio_500000000/realm/waterways/navigation_alternates/river_network/dawn_routes.md",
                         PHASE_BOOK_PATHS[0])

    def test_bounded_book_listing_and_real_manuscript_sha(self):
        a=list_books(domain="living_story",phase="ending_convergence",limit=8)
        b=list_books(domain="living_story",phase="ending_convergence",offset=8,limit=8)
        self.assertEqual(900,a["matched"])
        self.assertFalse({x["path"] for x in a["items"]}&{
                          x["path"] for x in b["items"]})
        with self.assertRaises(StudioError):
            list_books(limit=65)
        hashes=set()
        for i in range(10):
            book=receipt(*identity(i))
            self.assertIn("Fifty exact",book["markdown"])
            self.assertIn("Thirty objective",book["markdown"])
            self.assertEqual(5000,book["covered_commands"])
            hashes.add(book["content_sha256"])
        self.assertEqual(10,len(hashes))

    def test_export_actual_markdown_and_cryptographic_manifest(self):
        from scripts.export_game_studio_phase_handbooks import export
        with TemporaryDirectory() as dirname:
            result=export(Path(dirname),offset=0,limit=2)
            self.assertEqual(2,result["exported"])
            self.assertTrue(Path(result["first_manifest"]).is_file())
            self.assertTrue((Path(dirname)/PHASE_BOOK_PATHS[0]).is_file())


if __name__=="__main__":
    unittest.main()
