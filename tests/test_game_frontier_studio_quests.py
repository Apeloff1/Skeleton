"""Studio quest branch authoring and authored manifest integration."""
from dataclasses import replace
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioQuest,StudioQuestStage,StudioError,compile_studio_project,
    compile_studio_native_quest_graph,STUDIO_TOOLS,
)
from skeleton.jeeves.game_frontier_native_quest_session import (
    parse_native_quest_graph,
)
from tests.test_game_frontier_studio_zones import authored


def chapters():
    return (StudioQuest("quest_wind","Ascend the airways","start",(
        StudioQuestStage("start","Reach the sky island",("ridge","harbor")),
        StudioQuestStage("ridge","Navigate the updraft",("ending",)),
        StudioQuestStage("harbor","Take the ferry",("ending",)),
        StudioQuestStage("ending","Enter the observatory"),
    )),)


class StudioQuestTests(unittest.TestCase):
    def test_multi_branch_quest_compile_and_studio_manifest(self):
        source=replace(authored(),native_quests=chapters())
        compiled=compile_studio_native_quest_graph(source)
        self.assertEqual(compiled,parse_native_quest_graph(compiled))
        self.assertEqual(compiled["quests"][0]["stages"][0]["next"],
                         ["ridge","harbor"])
        self.assertEqual(compiled,compile_studio_native_quest_graph(source))
        manifest=compile_studio_project(source)
        self.assertEqual(manifest["native_quests"][0]["id"],"quest_wind")
        self.assertNotEqual(manifest["content_sha256"],
                            compile_studio_project(authored())["content_sha256"])
        self.assertIn("native_quest_graph_compiler",STUDIO_TOOLS)
        self.assertIn("native_approved_session_replay_inspector",STUDIO_TOOLS)

    def test_unresolved_stage_and_orphan_rejected_on_studio_authoring(self):
        for invalid in (
            StudioQuest("quest","title","start",(
                StudioQuestStage("start","do",("missing",)),)),
            StudioQuest("quest","title","wrong",(
                StudioQuestStage("start","do"),)),
            StudioQuest("quest","title","start",(
                StudioQuestStage("start","do"),
                StudioQuestStage("orphan","unused"))),
        ):
            with self.subTest(invalid=invalid),self.assertRaises(StudioError):
                replace(authored(),native_quests=(invalid,))

    def test_reject_duplicate_quest_and_malformed_stage(self):
        chapter=chapters()[0]
        with self.assertRaises(StudioError):
            replace(authored(),native_quests=(chapter,chapter))
        with self.assertRaises(StudioError):
            StudioQuestStage("bad stage","any")
        with self.assertRaises(StudioError):
            StudioQuest("x","title","start",())

    def test_empty_studio_quest_is_backwards_compatible(self):
        compiled=compile_studio_native_quest_graph(authored())
        self.assertEqual(compiled["quests"],[])
        self.assertEqual(len(compiled["receipt_digest"]),64)


if __name__=="__main__":
    unittest.main()
