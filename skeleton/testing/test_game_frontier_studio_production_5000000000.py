"""Five-billion composed game producers plus ranked million-book documentation.

Tests exact virtual IDs, 10 real campaign source transforms, 10-domain
integration, source-only gameplay/sensor constraints, immutable replay,
bounded ranked handbook rendering and manifest-backed exported artifacts.
A registered composition is not a finished native game.
"""
from __future__ import annotations

import json
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
from skeleton.forge.game_frontier_studio_campaign_production import (
    CAMPAIGN_ACTIONS,CAMPAIGNS,describe_campaign,search_campaigns,
)
from skeleton.forge.game_frontier_studio_phase_production import PHASE_ACTIONS
from skeleton.forge.game_frontier_studio_campaign_handbooks import (
    BOOK_COUNT,CAMPAIGN_BOOK_PATHS,identity,number,list_books,
    receipt,rank_variants,grade,metadata,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document,load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project,arguments,
)


class FiveBillionSourceAuthoring(unittest.TestCase):
    def test_virtual_indexes_and_legacy_orders(self):
        self.assertEqual(5_000_000_000,len(AUTHORING_ACTIONS))
        self.assertEqual(4_500_000_000,len(CAMPAIGN_ACTIONS))
        self.assertEqual(AUTHORING_ACTIONS[500_000_000],CAMPAIGN_ACTIONS[0])
        self.assertEqual(AUTHORING_ACTIONS[-1],CAMPAIGN_ACTIONS[-1])
        self.assertEqual(AUTHORING_ACTIONS[500_000_000:500_000_018],
                         CAMPAIGN_ACTIONS[:18])
        self.assertTrue(CAMPAIGN_ACTIONS[-1] in AUTHORING_ACTIONS)
        self.assertNotIn("campaign_exec_arbitrary_code________chapter_crossroads",
                         AUTHORING_ACTIONS)
        with self.assertRaises(IndexError):
            _=CAMPAIGN_ACTIONS[4_500_000_000]

    def test_exact_composite_identity_roundtrip(self):
        for i in (0,1,9,10,99,899,900,8999,500_000,50_000_000,
                  225_000_000,449_999_999):
            for campaign in range(10):
                action=CAMPAIGN_ACTIONS[i*10+campaign]
                expected=("campaign_"+PHASE_ACTIONS[i].removeprefix("phase_")
                          +"________"+CAMPAIGNS[campaign])
                self.assertEqual(expected,action)
                meta=describe_campaign(action)
                self.assertEqual(PHASE_ACTIONS[i],meta["base_operation"])
                self.assertEqual(CAMPAIGNS[campaign],meta["campaign"])
                self.assertLessEqual(len(action),256)
                self.assertTrue(meta["actual_project_mutation"])

    def test_ten_domains_by_ten_campaigns_produce_distinct_real_source(self):
        original=original_project()
        before=project_digest(original)
        for d in range(10):
            outcomes=set()
            for campaign in range(10):
                operation=CAMPAIGN_ACTIONS[d*450_000_000+campaign]
                with self.subTest(domain=d,campaign=campaign):
                    output=execute_authoring(original,operation,arguments(operation))
                    self.assertIsInstance(output,StudioProject)
                    self.assertNotEqual(before,project_digest(output))
                    self.assertGreater(len(output.environmental_pages),
                                       len(original.environmental_pages))
                    outcomes.add(project_digest(output))
            self.assertEqual(10,len(outcomes))
        self.assertEqual(before,project_digest(original))

    def test_observed_campaign_rpg_event_never_invents_quest_progress(self):
        base=original_project()
        operation=CAMPAIGN_ACTIONS[0]
        output=execute_authoring(base,operation,arguments(operation))
        page=output.environmental_pages[-1]
        self.assertEqual("advance_quest",page.actions[0].kind)
        self.assertEqual({"quest_progress","npc_reputation"},
                         {x.signal for x in page.conditions})
        good=evaluate_environment_events(
            (page,),current={"quest_progress":.75,"npc_reputation":25.},
            now_ms=20_000)
        self.assertEqual(1,len(good.accepted))
        self.assertTrue(good.required_runtime_approvals)
        low=evaluate_environment_events(
            (page,),current={"quest_progress":.0,"npc_reputation":0.},
            now_ms=20_000)
        self.assertEqual(0,len(low.accepted))

    def test_native_new_cast_and_quest_preserve_existing_canon(self):
        base=original_project()
        actors=execute_authoring(base,CAMPAIGN_ACTIONS[2*450_000_000+3],
               arguments(CAMPAIGN_ACTIONS[2*450_000_000+3]))
        self.assertEqual(base.placements,actors.placements[:len(base.placements)])
        self.assertEqual(len(base.placements)+4,len(actors.placements))
        scenes=execute_authoring(base,CAMPAIGN_ACTIONS[3*450_000_000+9],
               arguments(CAMPAIGN_ACTIONS[3*450_000_000+9]))
        quest=scenes.native_quests[-1]
        branches=[s for s in quest.stages if "_camp_" in s.stage_id]
        self.assertEqual(1,len(branches))
        self.assertIn(branches[0].stage_id,quest.stages[0].next_stage_ids)
        self.assertTrue(compile_studio_native_quest_graph(scenes)["quests"])

    def test_arithmetic_pagination_with_exact_filters(self):
        for start in (0,1,31,500_000,912_000_001,4_499_999_987):
            with self.subTest(offset=start):
                result=search_campaigns(offset=start,limit=32)
                self.assertEqual(
                    CAMPAIGN_ACTIONS[start:min(start+32,4_500_000_000)],
                    tuple(x["operation"] for x in result["items"]))
                self.assertEqual(4_500_000_000,result["matched"])
        result=search_campaigns(domain="stronghold",system_layer="stealth",
              director="audio_cues",finish="alternate_endings",
              worldline="sky_navigation",phase="storm_shelters",
              campaign="siege_campaigns",limit=8)
        self.assertEqual(450,result["matched"])
        self.assertEqual(8,len(result["items"]))
        with self.assertRaises(StudioError):
            search_campaigns(limit=65)
        with self.assertRaises(StudioError):
            search_campaigns(campaign="../../escape")

    def test_source_roundtrip_and_invalid_batch_rollback(self):
        base=original_project()
        name=CAMPAIGN_ACTIONS[8*450_000_000+8]
        a=execute_authoring(base,name,{**arguments(name),"instance_id":"partA"})
        b=execute_authoring(a,name,{**arguments(name),"instance_id":"partB"})
        self.assertEqual(len(base.native_quests)+2,len(b.native_quests))
        self.assertEqual(project_digest(b),project_digest(
            load_authored_document(authored_document(b),
                                   project_id=base.project_id)))
        with self.assertRaises(StudioError):
            execute_authoring(a,name,{**arguments(name),"instance_id":"partA"})
        with self.assertRaises(StudioError):
            apply_authoring_batch(base,[
                {"action":name,"parameters":arguments(name)},
                {"action":name,"parameters":{
                    **arguments(name),"instance_id":"../../escape"}},
            ])
        self.assertEqual(project_digest(base),project_digest(original_project()))

    def test_native_godot_source_export_uses_game_world_edits(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        base=original_project()
        name=CAMPAIGN_ACTIONS[5*450_000_000+4]
        output=execute_authoring(base,name,arguments(name))
        generated=compile_studio_expedition(
            output,ArchipelagoProfile(seed=31,islands=4,caverns=0,
                include_portals=False,include_underwater=False),
            include_godot=True,playtest_routes=2)
        self.assertIn("game/frontier/studio_terrain.gd",
                      generated["godot_project_files"])
        self.assertIn("game/frontier/studio_terrain.json",
                      generated["godot_project_files"])
        self.assertGreater(generated["travel_edges"],0)

    def test_source_catalog_keeps_bounded_summary(self):
        summary=authored_summary(original_project())
        self.assertEqual(500,len(summary["action_catalog"]))
        self.assertEqual(4_500_000_000,summary["campaign_recipe_count"])
        self.assertEqual(4_999_999_500,summary["recipe_catalog_count"])
        self.assertEqual(5_000_000_000,summary["catalog_total"])


class RankedMillionBookLibrary(unittest.TestCase):
    def test_900k_reversible_book_identities_and_distinct_paths(self):
        self.assertEqual(900_000,BOOK_COUNT)
        self.assertEqual(900_000,len(CAMPAIGN_BOOK_PATHS))
        for i in (0,1,9,10,99,10_000,444_444,899_999):
            identity_values=identity(i)
            self.assertEqual(i,number(*identity_values))
        self.assertEqual(
            "game_studio_5000000000/realm/waterways/navigation_alternates/river_network/dawn_routes/chapter_crossroads.md",
            CAMPAIGN_BOOK_PATHS[0])

    def test_rank_ten_rendered_manuals_quality_first_or_longest_first(self):
        context=identity(0)[:5]
        quality=rank_variants(*context,sort="quality")
        length=rank_variants(*context,sort="length")
        self.assertEqual(10,quality["compared"])
        self.assertEqual(10,length["compared"])
        self.assertEqual(set(CAMPAIGNS),{r["campaign"] for r in quality["items"]})
        self.assertEqual(
            sorted(quality["items"],
                   key=lambda r:(-r["quality_score"],-r["words"],r["campaign"])),
            quality["items"])
        self.assertEqual(
            sorted(length["items"],
                   key=lambda r:(-r["words"],-r["quality_score"],r["campaign"])),
            length["items"])
        self.assertTrue(all(0<=r["quality_score"]<=100 for r in quality["items"]))
        self.assertTrue(all(r["words"]>1000 for r in quality["items"]))
        self.assertEqual("ten_campaign_variants_for_one_exact_production_context",
                         quality["scope"])
        with self.assertRaises(StudioError):
            rank_variants(*context,sort="marketing_hype")

    def test_real_book_receipt_checks_quality_and_length(self):
        item=receipt(*identity(0))
        self.assertIn("Fifty implemented source archetypes",item["markdown"])
        self.assertEqual(item["covered_commands"],5000)
        self.assertEqual(len(item["content_sha256"]),64)
        self.assertGreater(item["words"],1000)
        self.assertEqual(item["bytes"],len(item["markdown"].encode("utf8")))
        self.assertEqual(item["quality_kind"],
            "objective_document_completeness_not_playability")
        self.assertTrue(item["criteria"]["fifty_archetypes"])

    def test_quality_score_requires_evidence_not_just_more_words(self):
        args=identity(0)
        manual=receipt(*args)
        self.assertTrue(manual["criteria"]["seven_required_sections"])
        erased=manual["markdown"].replace(
            "## Ten gameplay systems with actual execution examples",
            "## Unspecified gameplay",1)
        degraded=grade(erased,metadata(*args))
        self.assertLess(degraded["quality_score"],manual["quality_score"])
        padding=manual["markdown"]+"\\n"+("decorative verbosity "*2000)
        enlarged=grade(padding,metadata(*args))
        self.assertEqual(enlarged["quality_score"],manual["quality_score"])
        self.assertGreater(enlarged["words"],manual["words"])

    def test_paginated_book_discovery_and_real_batch_ranking_export(self):
        page=list_books(domain="living_story",campaign="epilogue_variants",limit=4)
        self.assertEqual(9_000,page["matched"])
        self.assertEqual(4,len(page["items"]))
        with self.assertRaises(StudioError):
            list_books(limit=100)
        from scripts.export_game_studio_campaign_handbooks import export
        with TemporaryDirectory() as temp:
            result=export(Path(temp),offset=0,limit=2)
            self.assertEqual(2,result["exported"])
            self.assertTrue(Path(result["ranking_file"]).is_file())
            self.assertTrue((Path(temp)/CAMPAIGN_BOOK_PATHS[0]).is_file())
            data=json.loads(Path(result["ranking_file"]).read_text())
            self.assertEqual("rendered_export_batch_only",data["scope"])
            self.assertEqual(2,len(data["ranking"]["quality"]))
            self.assertEqual(2,len(data["ranking"]["length"]))


if __name__=="__main__":
    unittest.main()
