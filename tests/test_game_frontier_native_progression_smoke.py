"""Exercise exact authored progression ordering in every native Godot fixture."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.build_game_frontier_smoke import build_smoke_project
from skeleton.jeeves.game_frontier_native_rpg_bridge import parse_native_rpg_pages
from skeleton.jeeves.game_frontier_native_quest_session import authored_page_digest


class NativeRPGProgressionSmokeTests(unittest.TestCase):
    def test_real_godot_fixture_awards_xp_before_unlock_and_records_faction(self):
        with TemporaryDirectory() as tmp:
            for fps in (30,50,60,120):
                folder=Path(tmp)/str(fps)
                folder.mkdir()
                build_smoke_project(folder,fps=fps,frames=20)
                source=json.loads((folder/"native_rpg_pages.json").read_text())
                pages=parse_native_rpg_pages(source)
                begin=next(p for p in pages if p.page_id=="begin_sky_trial")
                finish=next(p for p in pages if p.page_id=="complete_sky_trial")
                commands=[(a.kind,a.value) for a in begin.actions]
                self.assertLess(commands.index(("award_xp","100")),
                                commands.index(("unlock_skill","wind_dash:2")))
                self.assertIn(("set_faction_reputation","islanders:+25"),commands)
                self.assertIn(("award_xp","30"),
                              [(a.kind,a.value) for a in finish.actions])
                self.assertEqual(len(authored_page_digest(pages)),64)

    def test_level_and_skill_actions_are_not_automatically_world_authorized(self):
        from skeleton.jeeves.game_frontier_native_quest_session import _apply_page
        graph={"sky_trial":{"start":"departed","edges":{
            "departed":["finished"],"finished":[]}}}
        quests={}
        flags={}
        for kind,value in (("award_xp","100"),("unlock_skill","wind_dash:2"),
                           ("set_faction_reputation","islanders:+25")):
            quests,flags,cues=_apply_page(
                [{"kind":kind,"value":value,"target":"hero"}],
                actor_id="hero",graph=graph,quests=quests,flags=flags,frame=0)
            self.assertEqual(quests,{})
            self.assertEqual(flags,{})
            self.assertEqual(len(cues),1)
            self.assertEqual(cues[0]["state"],
                             "queued_for_explicit_engine_approval")
