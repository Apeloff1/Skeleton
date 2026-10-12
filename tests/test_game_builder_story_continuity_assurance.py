"""100-act 9999-scene production law, exact visual/voice/wardrobe memory."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest

from skeleton.ai.game_builder.story_canon_fabric import (
    SCENE,StoryCanonError,digest,sign,verify_story_history)
from skeleton.ai.game_builder.story_continuity_assurance import (
    CONTRACT, ACT_TARGET, SCENE_TARGET, QC_GATES, _history_root,
    _advance_root, _receipt, contract_template, validate_contract,
    seal_production_scene, verify_production_history, confirm_stage)
from skeleton.ai.game_builder.story_detail_history import detail_timeline
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from tests.test_game_builder_story_canon_fabric import canonical_bible,scene_source
from tests.test_game_builder_story_workspace import stages,write_reviewed


def original_contract(bible, with_item=False):
    source=contract_template(bible)
    source["human_design_reviewed"]=True
    for i,c in enumerate(source["characters"]):
        c.update(
            voice_id="voice_original_"+c["id"],
            voice_asset_sha256=sha256(("original-consented-reference-"+c["id"]).encode()).hexdigest(),
            voice_style="calm documentary voice for original historical fiction",
            language="English",accent="articulated original city accent",
            face_id="face_original_"+c["id"])
        c["facial_geometry"]={
            "eye_shape":"wide set angular eyes",
            "nose":"high nose bridge","jaw":"soft jaw curvature",
            "mouth":"distinctive upper lip outline",
            "skin_details":"small left-cheek skin marking"}
        c["expressions"]=[
            {"intent":"respectful reminder","expression":"determined"},
            {"intent":"empathetic silence","expression":"concern"}]
        costume=c["wardrobe"][0]
        costume.update(id="outfit_original_"+c["id"],
                       fabric="woven local flax",
                       details="three seams and a bronze circular clasp")
    for region in source["regions"]:
        region["style_id"]="style_"+region["id"]
        region["era"]="original astral historical era"
        region["style_notes"]="Every structure and material follows regional laws."
    if with_item:
        source["items"]=[{
            "id":"historical_table","asset":"map_table",
            "initial_owner":"alina",
            "details":"bronze circular engraved tabletop with source-verified patina",
            "style_id":"style_lantern_city"}]
    final=sign(source,CONTRACT)
    validate_contract(final,bible)
    return final


def observations(contract,bible,scene, *, extra_items=None, transfers=None):
    actor_profiles={x["id"]:x for x in contract["characters"]}
    profile=next(x for x in contract["regions"] if x["id"]==scene["region"])
    cast=[]
    for who in scene["cast"]:
        p=actor_profiles[who]
        costume=p["wardrobe"][0]
        cast.append({
            "character":who,"voice_id":p["voice_id"],
            "voice_asset_sha256":p["voice_asset_sha256"],
            "face_id":p["face_id"],
            "facial_geometry_digest":digest(p["facial_geometry"]),
            "outfit_id":costume["id"],
            "outfit_palette":costume["palette"],
            "dialogue_expressions":[{
                "line_id":d["id"],"intent":d["intent"],"expression":
                    next(rule["expression"] for rule in p["expressions"]
                         if rule["intent"]==d["intent"])
            } for d in scene["dialogue"] if d["speaker"]==who],
        })
    return {"cast":cast,"region":{
                "id":scene["region"],"style_id":profile["style_id"],
                "era":profile["era"],"palette":profile["palette"],
                "architecture":profile["architecture"]},
            "items":extra_items or [],"transfers":transfers or []}


class MeticulousProductionContinuityTests(unittest.TestCase):
    def setUp(self):
        self.bible=canonical_bible()
        self.contract=original_contract(self.bible)

    def test_exact_hundred_acts_and_9999_stage_contract_is_locked(self):
        self.assertEqual(ACT_TARGET,100)
        self.assertEqual(SCENE_TARGET,9999)
        self.assertGreaterEqual(len(QC_GATES),15)
        altered=deepcopy(self.contract)
        altered["scene_target"]=10000
        with self.assertRaises(StoryCanonError):
            validate_contract(sign(altered,CONTRACT),self.bible)
        altered=deepcopy(self.contract)
        altered["characters"][0]["voice_asset_sha256"]="absent"
        with self.assertRaises(StoryCanonError):
            validate_contract(sign(altered,CONTRACT),self.bible)
        altered=deepcopy(self.contract)
        altered["regions"][0]["architecture"]="invented replacement"
        with self.assertRaises(StoryCanonError):
            validate_contract(sign(altered,CONTRACT),self.bible)

    def test_one_scene_at_a_time_with_full_reparse_receipts(self):
        s1=scene_source(self.bible,1)
        first=seal_production_scene(self.bible,self.contract,[],s1,
                                    observations(self.contract,self.bible,s1))
        s2=scene_source(self.bible,2,first)
        second=seal_production_scene(self.bible,self.contract,[first],s2,
                                     observations(self.contract,self.bible,s2))
        check=verify_production_history(self.bible,self.contract,[first,second])
        self.assertEqual(check["accepted_scenes"],2)
        self.assertFalse(check["fully_completed"])
        self.assertEqual(check["verified_receipt_head"],second["assurance"]["digest"])
        self.assertEqual(second["assurance"]["previous_receipt_digest"],
                         first["assurance"]["digest"])
        self.assertEqual(second["assurance"]["passed_checks"],list(QC_GATES))
        self.assertTrue(check["all_prior_scenes_reparsed"])
        with self.assertRaises(StoryCanonError):
            seal_production_scene(self.bible,self.contract,[first],scene_source(
                self.bible,3,first),observations(self.contract,self.bible,s2))
        broken=deepcopy(first)
        broken["assurance"]["passed_checks"].pop()
        broken=sign(broken,SCENE)
        with self.assertRaises(StoryCanonError):
            verify_production_history(self.bible,self.contract,[broken,second])

    def test_immutable_voice_face_clothes_and_emotional_dialogue(self):
        scene=scene_source(self.bible,1)
        expected=observations(self.contract,self.bible,scene)
        for attack in ("voice","voice_hash","face","geometry",
                       "outfit","color","expression","line","era","architecture"):
            mutated=deepcopy(expected)
            actor=mutated["cast"][0]
            if attack=="voice":actor["voice_id"]="replacement_voice"
            elif attack=="voice_hash":actor["voice_asset_sha256"]="0"*64
            elif attack=="face":actor["face_id"]="different_person"
            elif attack=="geometry":actor["facial_geometry_digest"]="0"*64
            elif attack=="outfit":actor["outfit_id"]="invented_uniform"
            elif attack=="color":actor["outfit_palette"]=["#FFFFFF"]
            elif attack=="expression":actor["dialogue_expressions"][0]["expression"]="joy"
            elif attack=="line":actor["dialogue_expressions"][0]["line_id"]="later_dialogue"
            elif attack=="era":mutated["region"]["era"]="unrelated modern period"
            else:mutated["region"]["architecture"]="changed city architecture"
            with self.subTest(attack=attack),self.assertRaises(StoryCanonError):
                seal_production_scene(self.bible,self.contract,[],scene,mutated)

    def test_actual_historical_item_transfer_is_backlinked_to_story_event(self):
        contract=original_contract(self.bible,with_item=True)
        scene=scene_source(self.bible)
        base=next(x for x in self.bible["assets"] if x["id"]=="map_table")
        item={"id":"historical_table","owner":"boren",
              "asset_digest":digest(base),"style_id":"style_lantern_city",
              "palette":base["palette"]}
        change={"item":"historical_table","from_owner":"alina",
                "to_owner":"boren","event_ref":"arrival_1",
                "reason":"The story event transfers the real engraved tabletop."}
        good=observations(contract,self.bible,scene,
                          extra_items=[item],transfers=[change])
        confirmed=seal_production_scene(self.bible,contract,[],scene,good)
        self.assertEqual(verify_production_history(self.bible,contract,[confirmed])
                         ["current_item_owners"]["historical_table"],"boren")
        bad=deepcopy(good)
        bad["transfers"][0]["event_ref"]="nonexistent_future_scene"
        with self.assertRaises(StoryCanonError):
            seal_production_scene(self.bible,contract,[],scene,bad)
        bad=deepcopy(good);bad["items"]=[]
        with self.assertRaises(StoryCanonError):
            seal_production_scene(self.bible,contract,[],scene,bad)

    def test_real_reviewed_workspace_commits_need_immutable_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace=GameWorkspace.create(str(Path(folder)/"project"),authorized=True)
            workspace.create_project("worldforge","rpg",authorized=True)
            for phase in stages():
                write_reviewed(workspace,"game/story_bible.json",phase)
            write_reviewed(workspace,"game/continuity_contract.json",self.contract)
            source=scene_source(self.bible,1)
            with self.assertRaises(StoryCanonError):
                write_reviewed(workspace,
                    "story/scenes/act_0001/scene_000001.json",source)
            signed=seal_production_scene(self.bible,self.contract,[],source,
                                         observations(self.contract,self.bible,source))
            write_reviewed(workspace,"story/scenes/act_0001/scene_000001.json",signed)
            verified=confirm_stage(workspace,"worldforge")
            self.assertEqual(verified["accepted_scenes"],1)
            page=detail_timeline(workspace,"worldforge",character="alina")
            self.assertEqual(page["total_scene_occurrences"],1)
            self.assertEqual(page["immutable_source_profile"]["voice_id"],
                             "voice_original_alina")
            region=detail_timeline(workspace,"worldforge",region="lantern_city")
            self.assertEqual(region["occurrences"][0]["style"]["style_id"],
                             "style_lantern_city")
            with self.assertRaises(StoryCanonError):
                write_reviewed(workspace,"game/continuity_contract.json",sign(
                    {**self.contract,"human_design_reviewed":False},CONTRACT))

    def test_9999_linked_receipts_span_exactly_100_acts(self):
        # Stream-authored regression fixture: avoid quadratic per-commit replay
        # during construction, then independently verify *all* 9999 sources,
        # receipt links, character looks and dialogue intent in one full pass.
        state={x["id"]:dict(x["state"]) for x in self.bible["characters"]}
        items={}
        previous=None
        prior_receipt=None
        root=_history_root(self.bible,self.contract)
        scenes=[]
        for sequence in range(1,SCENE_TARGET+1):
            act=(sequence-1)//100+1
            number_in_act=(sequence-1)%100+1
            plain=scene_source(self.bible,sequence,previous)
            plain["act"]=act;plain["scene"]=number_in_act
            plain=sign(plain,SCENE)
            seen=observations(self.contract,self.bible,plain)
            receipt=_receipt(self.contract,plain,seen,prior_receipt,
                             state,state,items,items,root)
            sealed=sign({**plain,"assurance":receipt},SCENE)
            scenes.append(sealed)
            root=_advance_root(root,sealed,receipt)
            prior_receipt=receipt["digest"]
            previous=sealed
        result=verify_production_history(self.bible,self.contract,scenes)
        self.assertEqual(result["accepted_scenes"],9999)
        self.assertEqual(scenes[-1]["act"],100)
        self.assertEqual(scenes[-1]["scene"],99)
        self.assertTrue(result["fully_completed"])
        self.assertEqual(result["verified_receipt_head"],prior_receipt)
        self.assertEqual(result["verified_chain_head"],root)
        self.assertFalse(result["actual_voice_audio_verification_completed"])
        self.assertFalse(result["actual_rendered_facial_matching_completed"])

if __name__=="__main__":
    unittest.main()
