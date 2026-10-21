"""Fifty billion virtual source actions and nine million ranked chronicle books.

Assertions cover actual mutated source and native compiler output, not
marketing counts, mock platform gameplay, or trained model weight claims.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioProject, compile_studio_expedition,
    compile_studio_native_quest_graph,
)
from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, execute_authoring, project_digest,
    authored_summary, apply_authoring_batch,
)
from skeleton.forge.game_frontier_studio_campaign_production import (
    CAMPAIGN_ACTIONS,
)
from skeleton.forge.game_frontier_studio_chronicle_production import (
    CHRONICLE_ACTIONS, CHRONICLES, parent_action, describe_chronicle,
    search_chronicles,
)
from skeleton.forge.game_frontier_studio_chronicle_handbooks import (
    BOOK_COUNT, CHRONICLE_BOOK_PATHS, identity, number,
    list_books, receipt, rank_variants, grade, metadata,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project, arguments,
)

class FiftyBillionChronicleAuthoring(unittest.TestCase):
    def test_catalog_boundaries_and_legacy_stability(self):
        self.assertEqual(45_000_000_000, len(CHRONICLE_ACTIONS))
        self.assertEqual(500_000_000_000, len(AUTHORING_ACTIONS))
        self.assertEqual(CAMPAIGN_ACTIONS[0],AUTHORING_ACTIONS[500_000_000])
        self.assertEqual(CHRONICLE_ACTIONS[0],AUTHORING_ACTIONS[5_000_000_000])
        self.assertEqual(CHRONICLE_ACTIONS[-1],AUTHORING_ACTIONS[50_000_000_000-1])
        self.assertTrue(CHRONICLE_ACTIONS[-1] in AUTHORING_ACTIONS)
        self.assertNotIn("chronicle_exec_code_________first_arrival",AUTHORING_ACTIONS)
        with self.assertRaises(IndexError):
            _ = CHRONICLE_ACTIONS[45_000_000_000]

    def test_parent_roundtrip_and_exact_search(self):
        for pos in (0,1,9,10,99,1_000,125_999,
                    45_000_000,4_500_000_000,44_999_999_999):
            action=CHRONICLE_ACTIONS[pos]
            parent,axis=parent_action(action)
            self.assertEqual(CAMPAIGN_ACTIONS[pos//10],parent)
            self.assertEqual(CHRONICLES[pos%10],CHRONICLES[axis])
            self.assertEqual(action,describe_chronicle(action)["operation"])
            self.assertLessEqual(len(action),256)
        for offset in (0,1,64,4_555_555_555,44_999_999_967):
            page=search_chronicles(offset=offset,limit=32)
            self.assertEqual(tuple(item["operation"] for item in page["items"]),
                             CHRONICLE_ACTIONS[offset:offset+32])
        narrowed=search_chronicles(
            domain="realm",system_layer="stealth",
            director="audio_cues",finish="alternate_endings",
            worldline="sky_navigation",phase="storm_shelters",
            campaign="siege_campaigns",chronicle="emergency_response",
            limit=8)
        self.assertEqual(450,narrowed["matched"])
        self.assertEqual(8,len(narrowed["items"]))
        with self.assertRaises(StudioError):
            search_chronicles(chronicle="../../escape")
        with self.assertRaises(StudioError):
            search_chronicles(limit=100)
        with self.assertRaises(StudioError):
            search_chronicles(offset=45_000_000_001)

    def test_ten_axes_across_ten_real_source_domains(self):
        original=original_project()
        before=project_digest(original)
        for domain in range(10):
            digests=set()
            for chronicle in range(10):
                action=CHRONICLE_ACTIONS[domain*4_500_000_000+chronicle]
                with self.subTest(domain=domain,chronicle=chronicle):
                    result=execute_authoring(original,action,arguments(action))
                    self.assertIsInstance(result,StudioProject)
                    digest=project_digest(result)
                    self.assertNotEqual(before,digest)
                    self.assertGreater(len(result.environmental_pages),
                                       len(original.environmental_pages))
                    digests.add(digest)
            self.assertEqual(10,len(digests))
        self.assertEqual(before,project_digest(original))

    def test_observed_gameplay_predicate_and_native_approval(self):
        base=original_project()
        action=CHRONICLE_ACTIONS[0]
        edited=execute_authoring(base,action,arguments(action))
        page=edited.environmental_pages[-1]
        self.assertEqual(2,len(page.conditions))
        self.assertEqual({"quest_progress","npc_reputation"},
                         {condition.signal for condition in page.conditions})
        accepted=evaluate_environment_events(
            (page,),current={"quest_progress":.75,"npc_reputation":25.},
            now_ms=50_000)
        self.assertEqual(1,len(accepted.accepted))
        self.assertTrue(accepted.required_runtime_approvals)
        rejected=evaluate_environment_events(
            (page,),current={"quest_progress":0.0,"npc_reputation":0.0},
            now_ms=50_000)
        self.assertEqual(0,len(rejected.accepted))

    def test_new_cast_and_new_quest_without_prior_canon_changes(self):
        original=original_project()
        population=CHRONICLE_ACTIONS[2*4_500_000_000+3]
        cast=execute_authoring(original,population,arguments(population))
        self.assertEqual(original.placements,cast.placements[:len(original.placements)])
        self.assertGreater(len(cast.placements),len(original.placements))
        story=CHRONICLE_ACTIONS[3*4_500_000_000+9]
        authored=execute_authoring(original,story,arguments(story))
        self.assertEqual(original.native_quests,
                         authored.native_quests[:len(original.native_quests)])
        self.assertTrue(compile_studio_native_quest_graph(authored)["quests"])

    def test_transactional_save_roundtrip_and_atomic_rollback(self):
        original=original_project()
        action=CHRONICLE_ACTIONS[0]
        edited=execute_authoring(original,action,arguments(action))
        replay=load_authored_document(authored_document(edited),
                                      project_id=original.project_id)
        self.assertEqual(project_digest(edited),project_digest(replay))
        with self.assertRaises(StudioError):
            apply_authoring_batch(original,[
                {"action":action,"parameters":arguments(action)},
                {"action":action,"parameters":{
                    **arguments(action),"instance_id":"../../outside"}},
            ])
        self.assertEqual(project_digest(original),project_digest(original_project()))
        summary=authored_summary(edited)
        self.assertEqual(500,len(summary["action_catalog"]))
        self.assertEqual(45_000_000_000,summary["chronicle_recipe_count"])
        self.assertEqual(499_999_999_500,summary["recipe_catalog_count"])
        self.assertEqual(500_000_000_000,summary["catalog_total"])

    def test_actual_native_godot_world_source_export(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        base=original_project()
        action=CHRONICLE_ACTIONS[5*4_500_000_000+4]
        game=execute_authoring(base,action,arguments(action))
        emitted=compile_studio_expedition(
            game,ArchipelagoProfile(seed=31,islands=4,caverns=0,
                                    include_portals=False,include_underwater=False),
            include_godot=True,playtest_routes=2)
        self.assertIn("game/frontier/studio_terrain.gd",emitted["godot_project_files"])
        self.assertIn("game/frontier/studio_terrain.json",emitted["godot_project_files"])
        self.assertGreater(emitted["travel_edges"],0)

class TenMillionBooks(unittest.TestCase):
    def test_reversible_nine_million_new_source_identity_space(self):
        self.assertEqual(9_000_000,BOOK_COUNT)
        self.assertEqual(9_000_000,len(CHRONICLE_BOOK_PATHS))
        for i in (0,1,9,10,99,450_000,7_777_777,8_999_999):
            keys=identity(i)
            self.assertEqual(i,number(*keys))
            self.assertTrue(CHRONICLE_BOOK_PATHS[i].endswith(keys[-1]+".md"))
        self.assertEqual(
            "game_studio_50000000000/realm/waterways/navigation_alternates/river_network/dawn_routes/chapter_crossroads/first_arrival.md",
            CHRONICLE_BOOK_PATHS[0])

    def test_real_rendered_book_and_reproducible_sha(self):
        parts=identity(0)
        entry=receipt(*parts)
        self.assertEqual(5000,entry["covered_commands"])
        self.assertEqual(100,entry["quality_score"])
        self.assertEqual(50,entry["markdown"].count(" | chronicle_"))
        self.assertGreater(entry["words"],1000)
        self.assertEqual(entry["bytes"],len(entry["markdown"].encode("utf8")))
        self.assertEqual(entry["content_sha256"],
                         sha256(entry["markdown"].encode("utf8")).hexdigest())
        self.assertEqual(entry["content_sha256"],receipt(*parts)["content_sha256"])

    def test_quality_penalizes_missing_source_evidence_not_padding(self):
        parts=identity(0)
        orig=receipt(*parts)
        damaged=orig["markdown"].replace(
            "## Ten gameplay source examples","## Unrelated commentary",1)
        self.assertLess(grade(damaged,metadata(*parts))["quality_score"],
                        orig["quality_score"])
        padded=orig["markdown"] + "\n" + "empty filler " * 1000
        self.assertEqual(orig["quality_score"],
                         grade(padded,metadata(*parts))["quality_score"])
        self.assertGreater(grade(padded,metadata(*parts))["words"],orig["words"])

    def test_filtered_pagination_and_two_distinct_rank_orderings(self):
        found=list_books(domain="living_story",chronicle="renewal_and_return",limit=4)
        self.assertEqual(90_000,found["matched"])
        self.assertEqual(4,len(found["items"]))
        parts=identity(0)[:6]
        quality=rank_variants(*parts,sort="quality")
        length=rank_variants(*parts,sort="length")
        self.assertEqual(10,quality["compared"])
        self.assertEqual(10,length["compared"])
        self.assertEqual(set(CHRONICLES),
                         {row["chronicle"] for row in quality["items"]})
        self.assertEqual(quality["items"],
                         sorted(quality["items"],
                             key=lambda r:(-r["quality_score"],-r["words"],r["chronicle"])))
        self.assertEqual(length["items"],
                         sorted(length["items"],
                             key=lambda r:(-r["words"],-r["quality_score"],r["chronicle"])))
        with self.assertRaises(StudioError):
            rank_variants(*parts,sort="hype")
        with self.assertRaises(StudioError):
            list_books(limit=65)

    def test_materialized_markdown_manifest_and_ranked_receipts(self):
        from scripts.export_game_studio_chronicle_handbooks import export
        with TemporaryDirectory() as root:
            folder=Path(root)
            result=export(folder,offset=0,limit=2)
            self.assertEqual(2,result["exported"])
            self.assertTrue((folder/CHRONICLE_BOOK_PATHS[0]).is_file())
            manifest=json.loads(Path(result["manifest"]).read_text())
            self.assertEqual("actual_exported_batch_only",manifest["scope"])
            self.assertEqual(2,len(manifest["ranking"]["quality"]))
            self.assertEqual(2,len(manifest["ranking"]["length"]))
            first=manifest["receipts"][0]
            self.assertEqual(first["content_sha256"],
                             sha256((folder/first["path"]).read_bytes()).hexdigest())

if __name__=="__main__":
    unittest.main()
