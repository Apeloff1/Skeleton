"""Cross-file Jeeves production integration and explicit source custody."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace,WorkspaceError
from skeleton.ai.game_builder.story_canon_fabric import (
    BIBLE, SCENE, StoryCanonError, sign, story_bible_template, digest)
from skeleton.ai.game_builder.story_workspace import (
    load_story_workspace,validate_story_workspace_source,
    next_story_scene_template,story_workspace_brief,story_workspace_status)
from skeleton.ai.game_builder.game_prompt_router import route_game_prompt
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from tests.test_game_builder_story_canon_fabric import canonical_bible,scene_source

EMPTY=sha256(b"").hexdigest()


def write_reviewed(workspace, path, source, *, before=None):
    raw=json.dumps(source,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n"
    if before is None:
        try:
            before=workspace.read("current","worldforge",path)["version"]["sha256"]
        except WorkspaceError:
            before=EMPTY
    proposal=workspace.propose("worldforge",path,raw,
                               expected_sha256=before,
                               reason="Explicit original story world continuity review.",
                               authorized=True)
    return workspace.commit(proposal["proposal_id"],human_approved=True,
                            authorized=True)


def stages():
    complete=canonical_bible()
    base=story_bible_template("worldforge")
    base.update(title=complete["title"],story=complete["story"],world=complete["world"])
    foundation=sign(base,BIBLE)
    cast=deepcopy(base)
    cast.update(phase="cast",characters=complete["characters"])
    return foundation,sign(cast,BIBLE),complete


class JeevesWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.studio=GameWorkspace.create(str(Path(self.temp.name)/"workbench"),authorized=True)
        self.studio.create_project("worldforge","rpg",authorized=True)

    def commit_bible_phases(self):
        for phase in stages():
            write_reviewed(self.studio,"game/story_bible.json",phase)

    def test_progressive_story_cast_design_and_signed_source_history(self):
        foundation,cast,design=stages()
        with self.assertRaises(StoryCanonError):
            validate_story_workspace_source(self.studio,"worldforge",
                                             "game/story_bible.json",design)
        write_reviewed(self.studio,"game/story_bible.json",foundation)
        with self.assertRaises(StoryCanonError):
            validate_story_workspace_source(self.studio,"worldforge",
                                             "game/story_bible.json",design)
        write_reviewed(self.studio,"game/story_bible.json",cast)
        write_reviewed(self.studio,"game/story_bible.json",design)
        status=story_workspace_status(self.studio,"worldforge")
        self.assertEqual(status["phase"],"design")
        self.assertEqual(status["scenes_verified"],0)
        bible,history,index=load_story_workspace(self.studio,"worldforge")
        self.assertEqual(bible,design)
        first=scene_source(design)
        write_reviewed(self.studio,
            "story/scenes/act_0001/scene_000001.json",first)
        second=scene_source(design,2,first)
        write_reviewed(self.studio,
            "story/scenes/act_0001/scene_000002.json",second)
        status=story_workspace_status(self.studio,"worldforge")
        self.assertEqual(status["scenes_verified"],2)
        self.assertEqual(status["head_digest"],second["digest"])
        self.assertEqual(load_story_workspace(self.studio,"worldforge")[2]["scene_count"],2)
        prompt=story_workspace_brief(self.studio,"worldforge",
            cast=["alina","boren"],region="lantern_city",
            prompt="Continue scene three while preserving every historical clue.",
            max_bookmarks=2)
        self.assertEqual(prompt["next_sequence"],3)
        self.assertEqual(prompt["total_pair_history"],4)
        self.assertFalse(prompt["pair_history_complete_in_brief"])
        template=next_story_scene_template(self.studio,"worldforge",1,3)
        self.assertEqual(template["document"]["prior_digest"],second["digest"])
        self.assertFalse(template["write_authorized"])
        self.assertFalse(status["live_Jeeves_model_connected"])

    def test_story_scene_sabotage_stale_source_conflict_and_approval(self):
        self.commit_bible_phases()
        bible=canonical_bible()
        first=scene_source(bible)
        path="story/scenes/act_0001/scene_000001.json"
        bad=deepcopy(first)
        bad["assets"][0]["palette"]=["#FFFFFF"]
        with self.assertRaises(StoryCanonError):
            validate_story_workspace_source(self.studio,"worldforge",path,sign(bad,SCENE))
        with self.assertRaises(StoryCanonError):
            self.studio.propose("worldforge",path,json.dumps(sign(bad,SCENE)),
                expected_sha256=EMPTY,reason="Attempt to inject unsanctioned visual palette.",
                authorized=True)
        source=json.dumps(first)
        proposal=self.studio.propose("worldforge",path,source,
                expected_sha256=EMPTY,reason="Approve an original first scene draft.",
                authorized=True)
        with self.assertRaises(PermissionError):
            self.studio.commit(proposal["proposal_id"],
                               human_approved=False,authorized=True)
        self.studio.commit(proposal["proposal_id"],human_approved=True,authorized=True)
        with self.assertRaises(StoryCanonError):
            self.studio.propose("worldforge",path,json.dumps(first),
                expected_sha256=self.studio.read("current","worldforge",path)
                                ["version"]["sha256"],
                reason="Attempt an unversioned historical overwrite of act one.",
                authorized=True)
        with self.assertRaises(StoryCanonError):
            validate_story_workspace_source(self.studio,"worldforge",
                                             "game/story_bible.json",
                                             sign({**bible,"title":"Changed history"},BIBLE))
        with self.assertRaises(WorkspaceError):
            self.studio.propose("worldforge","story/scenes/../../../escape.json",
                 json.dumps(first),expected_sha256=EMPTY,
                 reason="Attempt to leave the project using a malicious path.",
                 authorized=True)

    def test_no_production_bible_can_bypass_foundation_on_first_commit(self):
        with self.assertRaises(StoryCanonError):
            write_reviewed(self.studio,"game/story_bible.json",canonical_bible())
        self.assertEqual(story_workspace_status(self.studio,"worldforge")["phase"],
                         "unstarted")

    def test_no_fake_scene_memory_when_bible_missing(self):
        self.assertEqual(story_workspace_status(self.studio,"worldforge")["phase"],
                         "unstarted")
        with self.assertRaises(StoryCanonError):
            story_workspace_brief(self.studio,"worldforge",
                    cast=["alina"],region="lantern_city",
                    prompt="Invent production history that does not exist in sources.")
        self.assertIn("Jeeves",render_workspace_html("A"*42).decode())
        plan=route_game_prompt(self.studio,"Keep the same story bible palette and scene 500 consistent.",
                               project="worldforge",authorized=True)
        self.assertIn("game/story_bible.json",[f.path for f in plan.files])
        self.assertFalse(plan.payload()["model_inference_performed"])

if __name__=="__main__":
    unittest.main()
