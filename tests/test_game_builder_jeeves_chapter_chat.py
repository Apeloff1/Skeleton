"""Fail-closed Jeeves chapter conversation across chat, Studio, and source receipts."""
from __future__ import annotations

from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.jeeves_chapter_chat import chat_turn
from skeleton.ai.game_builder.story_canon_fabric import StoryCanonError
from skeleton.ai.game_builder.story_continuity_assurance import seal_production_scene
from tests.test_game_builder_story_workspace import stages,write_reviewed
from tests.test_game_builder_story_continuity_assurance import (
    chapter_scene,original_contract,observations)


class JeevesChapterConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws=GameWorkspace.create(str(Path(self.tmp.name)/"studio"),
                                     authorized=True)
        self.ws.create_project("worldforge","rpg",authorized=True)

    def test_chained_human_chat_never_publishes_unreviewed_game_content(self):
        first=chat_turn(self.ws,"worldforge","Draft an original story foundation.")
        self.assertEqual(first["work_order"]["stage"],"foundation")
        self.assertFalse(first["model_inference_performed"])
        self.assertFalse(first["scene_autonomously_published"])
        self.assertIsNone(first["active_chapter"])
        second=chat_turn(self.ws,"worldforge","Keep unique story motifs.",
                         session=first["session"])
        self.assertEqual(second["session"]["turns"][-1]["sequence"],2)
        self.assertEqual(second["session"]["turns"][0]["digest"],
                         first["session"]["turns"][0]["digest"])
        self.assertEqual(second["session"]["turns"][-1]["previous_turn_digest"],
                         first["session"]["turns"][0]["digest"])

    def test_forged_transcript_and_stale_story_rejected(self):
        first=chat_turn(self.ws,"worldforge","Draft a new original premise.")
        edited=deepcopy(first["session"])
        edited["turns"][0]["prompt"]="Replace every character's original voice."
        with self.assertRaises(StoryCanonError):
            chat_turn(self.ws,"worldforge","Next.",session=edited)
        replaced=deepcopy(first["session"])
        replaced["project"]="other_world"
        with self.assertRaises(StoryCanonError):
            chat_turn(self.ws,"worldforge","Next.",session=replaced)
        foundation,_,_=stages()
        write_reviewed(self.ws,"game/story_bible.json",foundation)
        with self.assertRaises(StoryCanonError):
            chat_turn(self.ws,"worldforge","Continue.",session=first["session"])

    def test_locks_chapter_history_and_scenario_as_single_chat_source(self):
        for source in stages():
            write_reviewed(self.ws,"game/story_bible.json",source)
        design=stages()[-1]
        contract=original_contract(design)
        write_reviewed(self.ws,"game/continuity_contract.json",contract)
        first=chat_turn(self.ws,"worldforge",
            "Plan an original dramatic prologue and mark every plot point.",
            cast=["alina","boren"],region="lantern_city")
        self.assertEqual(first["work_order"]["stage"],"scene")
        self.assertEqual(first["work_order"]["source_template"]["chapter"],1)
        self.assertEqual(first["active_chapter"]["chapter"],1)
        self.assertEqual(first["active_chapter"]["chapter_highlighters"],[])
        original=chapter_scene(design)
        sealed=seal_production_scene(design,contract,[],original,
                                     observations(contract,design,original))
        write_reviewed(self.ws,"story/chapters/chapter_001/acts/act_0001/scene_000001.json",
                       sealed)
        with self.assertRaises(StoryCanonError):
            chat_turn(self.ws,"worldforge","Continue previous unrefreshed draft.",
                      session=first["session"])
        continued=chat_turn(self.ws,"worldforge",
            "Continue from the source-verified lantern clue and preserve the voice.",
            cast=["alina","boren"],region="lantern_city")
        self.assertEqual(continued["work_order"]["source_template"]["sequence"],2)
        self.assertEqual(continued["work_order"]["source_template"]["chapter"],1)
        self.assertEqual(continued["active_chapter"]["chapter_highlighters"][0]["id"],
                         "highlight_1")
        self.assertTrue(continued["active_chapter"]["all_previous_chapters_reparsed"])
        self.assertFalse(continued["active_chapter"]["model_inference_performed"])


if __name__=="__main__":
    unittest.main()
