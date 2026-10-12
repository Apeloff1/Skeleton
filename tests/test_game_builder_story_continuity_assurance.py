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



def chapter_scene(bible,sequence=1,previous=None):
    """Source-authored act/chapter fixture with explicit real plot bookmarks."""
    from skeleton.ai.game_builder.story_chapter_context import (
        storytelling_template,HIGHLIGHT_PALETTE)
    raw=scene_source(bible,sequence,previous)
    raw["chapter"]=(sequence-1)//100+1
    raw["act"]=(sequence-1)//10+1
    raw["scene"]=(sequence-1)%10+1
    chapter=raw["chapter"]
    start=(chapter-1)*100+1
    ending=sequence%100==0 or sequence==9999
    resolved=ending and chapter%2==0
    form=("prelude" if chapter%2==0 else "prologue") if sequence==start else (
          "interlude" if (sequence-start)%50==49 else "main")
    story=storytelling_template(chapter,form=form)
    story.update(
        chapter_title=f"The Lantern Chapter {chapter:03d}",
        pacing="rising" if sequence%2 else "aftermath",
        tension_before=5+(sequence-1)%2,
        tension_after=5+sequence%2,
        stakes="The travelers must protect an original historical trade route.",
        dramatic_question="Who can be trusted to preserve the original navigation ledger?",
        hook="The next annotated map reveals a troubling original clue.",
        chapter_outcome=("resolution" if resolved else "cliffhanger")
                        if ending else "ongoing",
        plot_highlights=[{
            "id":f"highlight_{sequence}","kind":"foreshadowing",
            "reference":f"visit_{sequence}",
            "color":HIGHLIGHT_PALETTE["foreshadowing"],
            "importance":5 if ending else 2,
            "note":"A source-linked clue echoes the cause of this original chapter.",
        }],
        closed_highlights=[f"highlight_{start}"] if resolved else [],
        editorial={
            "camera":"over_shoulder",
            "cut":"match_cut",
            "performance":"Subtle pauses reveal cautious trust and uncertainty.",
            "soundscape":"Original softly resonant lantern chimes and distant wind.",
            "continuity_notes":[
                "Retain original camera axis and canonical character clothing.",
                "Keep accent, mouth shapes and identity reference unchanged."],
        },
    )
    raw["storytelling"]=story
    return sign(raw,SCENE)


class MeticulousProductionContinuityTests(unittest.TestCase):
    def setUp(self):
        self.bible=canonical_bible()
        self.contract=original_contract(self.bible)

    def test_hundred_chapters_thousand_acts_and_9999_scenes_locked(self):
        self.assertEqual(ACT_TARGET,1000)
        self.assertEqual(self.contract["chapter_target"],100)
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
        s1=chapter_scene(self.bible,1)
        first=seal_production_scene(self.bible,self.contract,[],s1,
                                    observations(self.contract,self.bible,s1))
        s2=chapter_scene(self.bible,2,first)
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
        scene=chapter_scene(self.bible,1)
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
        scene=chapter_scene(self.bible)
        scene["events"][0]["kind"]="item_transfer"
        scene["events"][0]["summary"]=(
            "The historical_table passes from Alina to Boren under a witnessed transfer.")
        scene=sign(scene,SCENE)
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
        generic=deepcopy(scene)
        generic["events"][0]["kind"]="unrelated_observed_event"
        generic=sign(generic,SCENE)
        with self.assertRaises(StoryCanonError):
            seal_production_scene(self.bible,contract,[],generic,good)
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
            source=chapter_scene(self.bible,1)
            with self.assertRaises(StoryCanonError):
                write_reviewed(workspace,
                    "story/chapters/chapter_001/acts/act_0001/scene_000001.json",source)
            signed=seal_production_scene(self.bible,self.contract,[],source,
                                         observations(self.contract,self.bible,source))
            write_reviewed(workspace,"story/chapters/chapter_001/acts/act_0001/scene_000001.json",signed)
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

    def test_studio_api_requires_exact_source_review_before_receipt_approval(self):
        import http.client
        import threading
        from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
        from skeleton.ai.game_builder.story_workspace import next_story_scene_template
        with tempfile.TemporaryDirectory() as folder:
            ws=GameWorkspace.create(str(Path(folder)/"local_studio"),authorized=True)
            ws.create_project("worldforge","rpg",authorized=True)
            for phase in stages():
                write_reviewed(ws,"game/story_bible.json",phase)
            server=create_workspace_server(ws,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                def request(route,payload, *,token=True):
                    connection=http.client.HTTPConnection(
                        "127.0.0.1",server.server_port,timeout=15)
                    headers={"Host":"127.0.0.1:"+str(server.server_port),
                             "Content-Type":"application/json"}
                    if token:headers["X-Game-Studio-Token"]=server.secret
                    connection.request("POST",route,body=json.dumps(payload),
                                       headers=headers)
                    response=connection.getresponse()
                    status=response.status
                    body=json.loads(response.read())
                    connection.close()
                    return status,body
                request_source={"project":"worldforge"}
                self.assertEqual(request("/api/story-continuity-template",
                                         request_source,token=False)[0],403)
                status,template=request("/api/story-continuity-template",
                                        request_source)
                self.assertEqual(status,200)
                self.assertEqual(template["path"],"game/continuity_contract.json")
                status,signed_contract=request("/api/story-sign",{
                    "project":"worldforge","path":"game/continuity_contract.json",
                    "document":self.contract})
                self.assertEqual(status,200)
                self.assertFalse(signed_contract["write_authorized"])
                write_reviewed(ws,"game/continuity_contract.json",self.contract)
                with self.assertRaises(StoryCanonError):
                    next_story_scene_template(ws,"worldforge",2,1)
                status,draft=request("/api/story-scene-template",{
                    "project":"worldforge","act":1,"scene":1})
                self.assertEqual(status,200)
                self.assertEqual(draft["next_global_sequence"],1)
                source=chapter_scene(self.bible)
                seen=observations(self.contract,self.bible,source)
                altered=deepcopy(seen)
                altered["cast"][0]["voice_id"]="unapproved_voice"
                self.assertEqual(request("/api/story-sign",{
                    "project":"worldforge",
                    "path":"story/chapters/chapter_001/acts/act_0001/scene_000001.json",
                    "document":source,"observations":altered})[0],400)
                status,approved_scene=request("/api/story-sign",{
                    "project":"worldforge",
                    "path":"story/chapters/chapter_001/acts/act_0001/scene_000001.json",
                    "document":source,"observations":seen})
                self.assertEqual(status,200)
                self.assertEqual(approved_scene["document"]["assurance"]["sequence"],1)
                write_reviewed(ws,approved_scene["path"],approved_scene["document"])
                self.assertEqual(next_story_scene_template(
                    ws,"worldforge",1,2)["next_global_sequence"],2)
                self.assertEqual(request("/api/story-stage-confirmation",
                                         request_source)[1]["accepted_scenes"],1)
                status,detail=request("/api/story-detail-timeline",{
                    "project":"worldforge","character":"alina"})
                self.assertEqual(status,200)
                self.assertEqual(detail["immutable_source_profile"]["voice_id"],
                                 "voice_original_alina")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_9999_receipts_span_100_chapters_and_1000_acts(self):
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
            plain=chapter_scene(self.bible,sequence,previous)
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
        self.assertEqual(scenes[-1]["chapter"],100)
        self.assertEqual(scenes[-1]["act"],1000)
        self.assertEqual(scenes[-1]["scene"],9)
        self.assertEqual(result["closed_chapters"],100)
        self.assertEqual(result["indexed_plot_highlighters"],9999)
        self.assertTrue(result["fully_completed"])
        self.assertEqual(result["verified_receipt_head"],prior_receipt)
        self.assertEqual(result["verified_chain_head"],root)
        self.assertFalse(result["actual_voice_audio_verification_completed"])
        self.assertFalse(result["actual_rendered_facial_matching_completed"])

if __name__=="__main__":
    unittest.main()
