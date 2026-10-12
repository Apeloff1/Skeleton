"""Adversarial story-editor tests for 100 chapters, 1000 acts and 9999 scenes."""
from __future__ import annotations
from copy import deepcopy
import unittest

from skeleton.ai.game_builder.story_canon_fabric import SCENE,sign,StoryCanonError
from skeleton.ai.game_builder.story_chapter_context import (
    ACTS,CHAPTERS,SCENES,HIGHLIGHT_PALETTE,chapter_context,
    chapter_of_act,validate_chapter_history,validate_storytelling)
from skeleton.ai.game_builder.story_continuity_assurance import (
    _receipt,_history_root,_advance_root,verify_production_history,
    seal_production_scene)
from tests.test_game_builder_story_canon_fabric import canonical_bible
from tests.test_game_builder_story_continuity_assurance import (
    chapter_scene,original_contract,observations)


class ChapterDramaturgyTests(unittest.TestCase):
    def setUp(self):
        self.bible=canonical_bible()
        self.contract=original_contract(self.bible)

    def test_hundred_chapters_are_ten_global_acts_each(self):
        self.assertEqual((CHAPTERS,ACTS,SCENES),(100,1000,9999))
        self.assertEqual(chapter_of_act(1),1)
        self.assertEqual(chapter_of_act(10),1)
        self.assertEqual(chapter_of_act(11),2)
        self.assertEqual(chapter_of_act(999),100)
        self.assertEqual(chapter_of_act(1000),100)
        for not_an_act in (0,1001,1.5,True,"100"):
            with self.subTest(not_an_act=not_an_act),self.assertRaises(StoryCanonError):
                chapter_of_act(not_an_act)

    def test_editor_rejects_fake_highlighters_inconsistent_colors_and_weak_stakes(self):
        original=chapter_scene(self.bible)
        assert original["storytelling"]["form"]=="prologue"
        for name,mod in (
            ("fake history",lambda t:t["plot_highlights"][0].update(
                reference="nonexistent_dialogue")),
            ("color mismatch",lambda t:t["plot_highlights"][0].update(
                color="#FFFFFF")),
            ("empty stakes",lambda t:t.update(stakes="")),
            ("empty hook",lambda t:t.update(hook="Mystery")),
            ("wrong first form",lambda t:t.update(form="interlude")),
            ("fake chapter",lambda t:None),
            ("false resolution",lambda t:t.update(chapter_outcome="resolution")),
            ("invalid camera",lambda t:t["editorial"].update(camera="teleport")),
            ("no continuity note",lambda t:t["editorial"].update(continuity_notes=[])),
            ("unapproved closure",lambda t:t.update(closed_highlights=["invented"])),
        ):
            with self.subTest(case=name):
                scene=deepcopy(original)
                if name=="fake chapter":scene["chapter"]=2
                else:mod(scene["storytelling"])
                scene=sign(scene,SCENE)
                with self.assertRaises(StoryCanonError):
                    validate_chapter_history([scene])

    def test_false_chapter_ending_and_suspense_reset_are_rejected(self):
        first=chapter_scene(self.bible,1)
        second=chapter_scene(self.bible,2,first)
        changed=deepcopy(second)
        changed["storytelling"]["tension_before"]=0
        with self.assertRaises(StoryCanonError):
            validate_chapter_history([first,sign(changed,SCENE)])
        changed=deepcopy(first)
        changed["storytelling"]["chapter_outcome"]="cliffhanger"
        with self.assertRaises(StoryCanonError):
            validate_chapter_history([sign(changed,SCENE),second])
        changed=deepcopy(second)
        changed["storytelling"]["form"]="prelude"
        with self.assertRaises(StoryCanonError):
            validate_chapter_history([first,sign(changed,SCENE)])

    def test_source_chapter_closure_capsules_and_unresolved_highlighters(self):
        character_state={c["id"]:dict(c["state"]) for c in self.bible["characters"]}
        root=_history_root(self.bible,self.contract)
        head=None
        previous=None
        scenes=[]
        for number in range(1,102):
            source=chapter_scene(self.bible,number,previous)
            evidence=observations(self.contract,self.bible,source)
            receipt=_receipt(self.contract,source,evidence,head,
                character_state,character_state,{}, {},root)
            sealed=sign({**source,"assurance":receipt},SCENE)
            scenes.append(sealed)
            root=_advance_root(root,sealed,receipt)
            head=receipt["digest"]
            previous=sealed
        projection=validate_chapter_history(scenes)
        self.assertEqual(projection["current_chapter"],2)
        self.assertEqual(projection["closed_chapters"][1]["ending"],"cliffhanger")
        self.assertEqual(len(projection["highlights"]),101)
        self.assertTrue(projection["rising_tension_by_chapter"][1])
        active=chapter_context(self.bible,self.contract,scenes)
        self.assertEqual(active["chapter_scene_count"],1)
        self.assertEqual(active["chapter"],2)
        self.assertEqual(active["chapter_highlighters"][0]["reference"],"visit_101")
        self.assertEqual(active["prior_chapter_endings"][0]["ending"],"cliffhanger")
        self.assertEqual(len(active["unresolved_prior_highlighters"]),100)
        self.assertEqual(active["verified_receipt_head"],head)
        previous_context=chapter_context(self.bible,self.contract,scenes,chapter=1)
        self.assertEqual(previous_context["chapter_scene_count"],100)
        self.assertEqual(previous_context["chapter_highlighters"][0]["color"],
                         HIGHLIGHT_PALETTE["foreshadowing"])
        with self.assertRaises(StoryCanonError):
            chapter_context(self.bible,self.contract,scenes,chapter=3)

    def test_prologues_and_interludes_keep_original_suspense_intent(self):
        previous=None
        for seq in range(1,102):
            source=chapter_scene(self.bible,seq,previous)
            if seq==1:self.assertEqual(source["storytelling"]["form"],"prologue")
            if seq==50:self.assertEqual(source["storytelling"]["form"],"interlude")
            if seq==100:
                self.assertEqual(source["storytelling"]["chapter_outcome"],
                                 "cliffhanger")
            if seq==101:self.assertEqual(source["storytelling"]["form"],"prelude")
            previous=source


if __name__=="__main__":
    unittest.main()
