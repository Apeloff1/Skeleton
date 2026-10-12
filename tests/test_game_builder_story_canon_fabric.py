"""Jeeves AI game *authoring* continuity: canon, memory, palettes, causality."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.story_canon_fabric import (
    BIBLE, SCENE, StoryCanonError, story_bible_template, validate_story_bible,
    story_scene_template, sign, digest, scene_path, verify_story_history,
    verify_story_scene, jeeves_story_brief,
)


def canonical_bible():
    base = story_bible_template("worldforge")
    base.update(phase="design", title="The Lantern Cartographer",
                story={"premise":"A surveyor restores the lost routes between quiet cities.",
                       "conflict":"The archives and council disagree on what should be saved.",
                       "themes":["memory", "community", "responsibility"],
                       "planned_chapters":100,"planned_acts":1000},
                world={"era":"original hybrid astronomical age",
                       "geography":"Lantern cities linked by stone-traced crossings.",
                       "laws":["Light needs a physical source.",
                               "Characters cannot travel without an authored transition."]},
                characters=[
                    {"id":"alina","name":"Alina","role":"cartographer",
                     "personality":"patient and observant",
                     "motivation":"protect real routes between cities",
                     "appearance":{"hair":"black braid","eyes":"amber",
                                   "silhouette":"tall with sturdy boots",
                                   "outfit":"blue surveyor coat",
                                   "palette":["#113355","#CC9944"]},
                     "state":{"status":"alive","location":"lantern_city",
                              "affiliation":"surveyors","outfit":"blue surveyor coat"}},
                    {"id":"boren","name":"Boren","role":"archivist",
                     "personality":"careful but curious",
                     "motivation":"preserve accounts of what occurred",
                     "appearance":{"hair":"silver crop","eyes":"green",
                                   "silhouette":"short and compact",
                                   "outfit":"bronze waistcoat",
                                   "palette":["#997744","#337744"]},
                     "state":{"status":"alive","location":"lantern_city",
                              "affiliation":"archive","outfit":"bronze waistcoat"}}],
                regions=[
                    {"id":"lantern_city","theme":"amber astronomical masonry",
                     "palette":["#113355","#CC9944","#997744","#337744"],
                     "architecture":"polygonal towers","lighting":"gas-lantern dusk",
                     "materials":["brass","stone","glass"]},
                    {"id":"orchard","theme":"soft emerald woodlands",
                     "palette":["#337744","#779955"],
                     "architecture":"raised timber walks","lighting":"misty spring",
                     "materials":["wood","moss"]}],
                assets=[
                    {"id":"map_table","kind":"prop","region":"lantern_city",
                     "palette":["#997744","#CC9944"],
                     "spec":"An original folding circular engraved map table.",
                     "identity":"Three collapsible telescopic legs.",
                     "rights":"original_reviewed","references":[]},
                    {"id":"borrowed_tower","kind":"environment","region":"lantern_city",
                     "palette":["#113355"],
                     "spec":"Original tall glass tower to be reviewed.",
                     "identity":"Thin branching lantern ribs.",
                     "rights":"review_required","references":[]}],
                inspiration=[
                    {"id":"genre_almanac","digest":"a"*64,"license":"licensed analysis notes",
                     "usage":"Abstract design principles, no copied plots or characters.",
                     "reviewed":True}],
                rights_reviewed=True)
    return sign(base, BIBLE)


def scene_source(bible, sequence=1, previous=None):
    doc = story_scene_template(bible, sequence=sequence, act=1, scene=sequence)
    doc.update(prior_digest=previous["digest"] if previous else None,
               title="Original scene "+str(sequence), region="lantern_city",
               cast=["alina", "boren"],
               looks=[
                   {"character": row["id"],
                    "appearance_digest":digest(row["appearance"]),
                    "palette":row["appearance"]["palette"],
                    "outfit":row["appearance"]["outfit"]}
                   for row in bible["characters"]],
               assets=[{"asset":"map_table","region":"lantern_city",
                        "palette":["#997744","#CC9944"]}],
               events=[
                   {"id":"arrival_"+str(sequence),"actor":"alina",
                    "kind":"observed_event",
                    "summary":"The cartographer records this original visit.",
                    "references":["visit_"+str(sequence-1)] if sequence>1 else [],
                    "changes":[]}],
               dialogue=[
                   {"id":"line_"+str(sequence),"speaker":"alina",
                    "listener":"boren","text":"The route remains ours to map.",
                    "intent":"respectful reminder",
                    "references":["exchange_"+str(sequence-1)] if sequence>1 else []}],
               interactions=[
                   {"id":"exchange_"+str(sequence),"actor":"alina","target":"boren",
                    "kind":"cooperation",
                    "summary":"They compare their original field notes.",
                    "references":["line_"+str(sequence)]}],
               beats=[
                   {"id":"visit_"+str(sequence),
                    "summary":"A new scene advances the authored story.",
                    "references":["arrival_"+str(sequence)]}])
    return sign(doc, SCENE)


class StoryCanonProductionTests(unittest.TestCase):
    def test_stage_gate_requires_story_before_cast_before_design(self):
        complete=canonical_bible()
        self.assertEqual(validate_story_bible(complete),complete)
        initial=story_bible_template("worldforge")
        initial.update(title=complete["title"],story=complete["story"],
                       world=complete["world"])
        first=sign(initial,BIBLE)
        validate_story_bible(first)
        second=deepcopy(initial)
        second.update(phase="cast",characters=complete["characters"])
        validate_story_bible(sign(second,BIBLE))
        premature=deepcopy(second)
        premature["regions"]=complete["regions"]
        with self.assertRaises(StoryCanonError):
            validate_story_bible(sign(premature,BIBLE))
        unlicensed=deepcopy(complete);unlicensed["rights_reviewed"]=False
        with self.assertRaises(StoryCanonError):
            validate_story_bible(sign(unlicensed,BIBLE))

    def test_scene_one_scene_five_hundred_cross_reference(self):
        bible=canonical_bible()
        history=[]
        prior=None
        for sequence in range(1,501):
            source=scene_source(bible,sequence,prior)
            history.append(source)
            prior=source
        result=verify_story_history(bible,history)
        self.assertEqual(result["scene_count"],500)
        self.assertEqual(result["characters"]["alina"][0],1)
        self.assertEqual(result["characters"]["alina"][-1],500)
        pair=result["pairs"]["alina:boren"]
        self.assertEqual(pair[0]["sequence"],1)
        self.assertEqual(pair[-1]["sequence"],500)
        self.assertEqual(result["bookmarks"]["exchange_1"]["path"],
                         "story/scenes/act_0001/scene_000001.json")
        self.assertEqual(result["bookmarks"]["exchange_500"]["path"],
                         "story/scenes/act_0001/scene_000500.json")
        self.assertEqual(result["assets"]["map_table"][-1],500)
        self.assertFalse(result["neural_weights_modified"])

    def test_next_scene_consistency_and_source_digest_are_enforced(self):
        bible=canonical_bible()
        first=scene_source(bible)
        second=scene_source(bible,2,first)
        self.assertTrue(verify_story_scene(bible,[first],second)["valid"])
        forged=deepcopy(second);forged["prior_digest"]="0"*64
        with self.assertRaises(StoryCanonError):
            verify_story_scene(bible,[first],sign(forged,SCENE))
        wrong=deepcopy(second);wrong["bible_digest"]="f"*64
        with self.assertRaises(StoryCanonError):
            verify_story_scene(bible,[first],sign(wrong,SCENE))
        missing=deepcopy(second);missing["sequence"]=3
        with self.assertRaises(StoryCanonError):
            verify_story_scene(bible,[first],sign(missing,SCENE))

    def test_cast_identity_wardrobe_scene_and_asset_colors_are_laws(self):
        bible=canonical_bible()
        source=scene_source(bible)
        for attack in ("look","outfit","color","asset","region","rights"):
            changed=deepcopy(source)
            if attack=="look":changed["looks"][0]["appearance_digest"]="0"*64
            elif attack=="outfit":changed["looks"][0]["outfit"]="purple armor"
            elif attack=="color":changed["looks"][0]["palette"]=["#FFFFFF"]
            elif attack=="asset":changed["assets"][0]["palette"]=["#FFFFFF"]
            elif attack=="region":changed["assets"][0]["region"]="orchard"
            else:changed["assets"][0]["asset"]="borrowed_tower"
            with self.subTest(attack=attack),self.assertRaises(StoryCanonError):
                verify_story_history(bible,[sign(changed,SCENE)])

    def test_character_death_travel_and_dialogue_require_causes(self):
        bible=canonical_bible()
        source=scene_source(bible)
        source["events"][0]["changes"].append(
            {"character":"alina","field":"status","previous":"alive",
             "value":"dead","reason":"An explicitly authored story death."})
        with self.assertRaises(StoryCanonError):
            verify_story_history(bible,[sign(source,SCENE)])
        source=scene_source(bible)
        source["region"]="orchard"
        with self.assertRaises(StoryCanonError):
            verify_story_history(bible,[sign(source,SCENE)])
        source=scene_source(bible)
        source["dialogue"][0]["references"]=["imagined_future"]
        with self.assertRaises(StoryCanonError):
            verify_story_history(bible,[sign(source,SCENE)])
        source=scene_source(bible)
        source["events"][0]["changes"].append(
            {"character":"alina","field":"status","previous":"alive",
             "value":"missing","reason":"An authored disappearance."})
        verify_story_history(bible,[sign(source,SCENE)])

    def test_jeeves_retrieves_bookmarked_relationship_not_fake_perfect_memory(self):
        bible=canonical_bible()
        prev=scene_source(bible)
        second=scene_source(bible,2,prev)
        result=jeeves_story_brief(bible,[prev,second],
                 cast=["alina","boren"],region="lantern_city",
                 request="Write scene three based on all prior witnessed dialogue.",
                 max_bookmarks=1)
        self.assertEqual(result["total_pair_history"],4)
        self.assertFalse(result["pair_history_complete_in_brief"])
        self.assertTrue(result["full_bookmarks_resolvable_in_index"])
        self.assertEqual(len(result["pair_history"]),1)
        self.assertEqual(result["next_sequence"],3)
        self.assertFalse(result["model_inference_performed"])
        self.assertFalse(result["source_changes_approved"])

    def test_legal_metadata_not_false_copyright_certification(self):
        bible=canonical_bible()
        bad=deepcopy(bible)
        bad["inspiration"][0]["reviewed"]=False
        with self.assertRaises(StoryCanonError):
            validate_story_bible(sign(bad,BIBLE))
        bad=deepcopy(bible)
        bad["assets"][0]["palette"]=["#AABBCC"]
        with self.assertRaises(StoryCanonError):
            validate_story_bible(sign(bad,BIBLE))
        scene=scene_source(bible)
        self.assertEqual(scene_path(scene),"story/scenes/act_0001/scene_000001.json")

if __name__=="__main__":
    unittest.main()
