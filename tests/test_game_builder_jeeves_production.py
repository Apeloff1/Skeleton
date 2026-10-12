"""Real Jeeves authoring work orders, historical memory and original asset queues."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.story_canon_fabric import StoryCanonError,digest,sign,BIBLE,SCENE
from skeleton.ai.game_builder.story_memory import (
    retrieve_bookmarks,character_memory_page,asset_identity_history)
from skeleton.ai.game_builder.jeeves_production_director import (
    work_order,planned_asset_orders,WORK_UNITS,ASSET_JOB_KINDS)
from tests.test_game_builder_story_canon_fabric import canonical_bible,scene_source
from tests.test_game_builder_story_workspace import stages,write_reviewed


class JeevesProductionContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws=GameWorkspace.create(str(Path(self.temp.name)/"workbench"),authorized=True)
        self.ws.create_project("worldforge","rpg",authorized=True)

    def test_chat_turns_follow_unskippable_story_cast_design_sequence(self):
        first=work_order(self.ws,"worldforge",
                         "Outline an original hundred-act story with strict lore consistency.")
        self.assertEqual(first["stage"],"foundation")
        self.assertEqual(first["target_path"],"game/story_bible.json")
        self.assertFalse(first["model_inference_performed"])
        self.assertFalse(first["source_files_changed"])
        foundation,cast,design=stages()
        write_reviewed(self.ws,"game/story_bible.json",foundation)
        second=work_order(self.ws,"worldforge",
                  "Build a cast of distinctive original characters and their histories.")
        self.assertEqual(second["stage"],"cast")
        self.assertEqual(second["predecessor_source_digests"],[foundation["digest"]])
        write_reviewed(self.ws,"game/story_bible.json",cast)
        third=work_order(self.ws,"worldforge",
                  "Design styled worlds, colors, items, environments, music and abilities.")
        self.assertEqual(third["stage"],"design")
        self.assertEqual(third["source_template"]["phase"],"design")
        self.assertEqual(third["predecessor_source_digests"],[cast["digest"]])
        write_reviewed(self.ws,"game/story_bible.json",design)
        fourth=work_order(self.ws,"worldforge",
                  "Write the first dramatic original scene with all correct dialogue.",
                  cast=["alina","boren"],region="lantern_city")
        self.assertEqual(fourth["stage"],"scene")
        self.assertEqual(fourth["target_path"],
                         "story/scenes/act_0001/scene_000001.json")
        self.assertEqual(fourth["source_template"]["sequence"],1)
        self.assertEqual(fourth["source_context"]["full_canon_brief"]["next_sequence"],1)
        self.assertIn("wiki_story_facts",fourth["independent_review_required"])
        self.assertFalse(fourth["human_authority_not_delegated"] is False)
        self.assertFalse(fourth["provider_connected_by_this_call"])

    def test_exact_cross_scene_memory_and_relationship_pagination(self):
        for stage in stages():
            write_reviewed(self.ws,"game/story_bible.json",stage)
        bible=canonical_bible()
        previous=None
        for i in range(1,8):
            s=scene_source(bible,i,previous)
            write_reviewed(self.ws,
                     f"story/scenes/act_0001/scene_{i:06d}.json",s)
            previous=s
        recalled=retrieve_bookmarks(self.ws,"worldforge",
                                    ["line_1","exchange_7","visit_4"])
        self.assertEqual(recalled["requested_count"],3)
        self.assertEqual(recalled["records"][0]["value"]["text"],
                         "The route remains ours to map.")
        self.assertEqual(recalled["records"][1]["source"]["sequence"],7)
        self.assertEqual(recalled["records"][2]["kind"],"beats")
        self.assertFalse(recalled["memory_invented"])
        self.assertEqual(digest({k:v for k,v in recalled.items()
                                 if k!="digest"}),recalled["digest"])
        page=character_memory_page(self.ws,"worldforge","alina",
                                   partner="boren",limit=3)
        self.assertEqual(page["total"],14)
        self.assertEqual(page["next_offset"],3)
        self.assertFalse(page["historical_memory_complete_in_page"])
        second=character_memory_page(self.ws,"worldforge","alina",
                                     partner="boren",offset=3,limit=50)
        self.assertEqual(second["total"],14)
        self.assertIsNone(second["next_offset"])
        self.assertEqual(len(set(page["references"]+second["references"])),14)
        self.assertEqual(len(character_memory_page(self.ws,"worldforge",
                             "boren",limit=50)["references"]),14)
        with self.assertRaises(StoryCanonError):
            retrieve_bookmarks(self.ws,"worldforge",["invented_future"])
        with self.assertRaises(StoryCanonError):
            retrieve_bookmarks(self.ws,"worldforge",["line_1","line_1"])
        with self.assertRaises(StoryCanonError):
            character_memory_page(self.ws,"worldforge","absent")

    def test_ai_asset_generation_queue_respects_provenance_and_palette(self):
        for stage in stages():
            write_reviewed(self.ws,"game/story_bible.json",stage)
        plan=planned_asset_orders(self.ws,"worldforge",
                      "Create consistent original prop and scenery production work.")
        self.assertEqual(plan["total_matching"],2)
        self.assertFalse(plan["native_assets_generated"])
        good,bad=plan["jobs"]
        self.assertEqual(good["asset"],"map_table")
        self.assertTrue(good["generation_allowed"])
        self.assertEqual(bad["asset"],"borrowed_tower")
        self.assertFalse(bad["generation_allowed"])
        self.assertEqual(bad["blocked_reason"],"rights_review_required")
        with self.assertRaises(StoryCanonError):
            planned_asset_orders(self.ws,"worldforge",
                   "Copy a licensed character without approval.", kinds=["trademark_clone"])
        with self.assertRaises(StoryCanonError):
            planned_asset_orders(self.ws,"worldforge",
                   "Generate an asset in an invented place.", region="not_canon")
        before=asset_identity_history(self.ws,"worldforge","map_table")
        self.assertEqual(before["scene_count"],0)
        self.assertFalse(before["appearance_consistency_verified"])
        s=scene_source(canonical_bible())
        write_reviewed(self.ws,"story/scenes/act_0001/scene_000001.json",s)
        after=asset_identity_history(self.ws,"worldforge","map_table")
        self.assertEqual(after["scenes"],[1])
        self.assertTrue(after["appearance_consistency_verified"])
        self.assertEqual(after["asset_source_digest"],digest(canonical_bible()["assets"][0]))

    def test_jeeves_plan_knows_sequential_canon_history_without_generating_it(self):
        for stage in stages():
            write_reviewed(self.ws,"game/story_bible.json",stage)
        old=scene_source(canonical_bible())
        write_reviewed(self.ws,"story/scenes/act_0001/scene_000001.json",old)
        order=work_order(self.ws,"worldforge",
             "Continue from the first act without changing the cartographer's appearance.",
             cast=["alina","boren"],region="lantern_city")
        self.assertEqual(order["target_path"],
                         "story/scenes/act_0001/scene_000002.json")
        self.assertEqual(order["source_template"]["prior_digest"],old["digest"])
        self.assertEqual(order["source_context"]["history_head_digest"],old["digest"])
        self.assertEqual(order["source_context"]["full_canon_brief"]["total_pair_history"],2)
        with self.assertRaises(StoryCanonError):
            work_order(self.ws,"worldforge",
                "Enter scene 900 before earlier chapters are written.",
                act=100,scene=9999,cast=["alina"],region="missing")
        after=work_order(self.ws,"worldforge",
             "Outline a new scene with no generated dialogue and mark missing cast.",
             act=1,scene=2)
        self.assertTrue(after["source_context"]["requires_cast_and_region_before_generation"])
        self.assertFalse(after["source_files_changed"])

if __name__ == "__main__":
    unittest.main()
