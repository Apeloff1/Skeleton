"""Adversarial checks for independent XP, skills and faction source reducer."""
from copy import deepcopy
import unittest

from skeleton.jeeves.game_frontier_native_quest_session import NativeQuestSessionError
from skeleton.jeeves.game_frontier_native_progression_audit import audit_native_progression
from tests.test_game_frontier_native_engine_dispatch import NativeEngineDispatchTests


def case():
    commands=[]
    for frame,kind,value in (
        (0,"award_xp","80"),(1,"award_xp","30"),
        (2,"unlock_skill","wind_dash:2"),
        (3,"set_faction_reputation","islanders:+30"),
        (4,"set_faction_reputation","islanders:-10"),
    ):
        commands.append({
            "frame":frame,"page_id":"story","target":"hero",
            "kind":kind,"value":value,
            "native_frame_receipt_digest":"a"*64,
        })
    progression=[
        dict(frame=0,page_id="story",kind="award_xp",value="80",
             resulting_xp=80,resulting_level=1,source_frame_digest="a"*64),
        dict(frame=1,page_id="story",kind="award_xp",value="30",
             resulting_xp=110,resulting_level=2,source_frame_digest="a"*64),
        dict(frame=2,page_id="story",kind="unlock_skill",value="wind_dash:2",
             resulting_xp=110,resulting_level=2,source_frame_digest="a"*64),
    ]
    factions=[
        dict(frame=3,page_id="story",faction="islanders",value="islanders:+30",
             resulting_reputation=30,source_frame_digest="a"*64),
        dict(frame=4,page_id="story",faction="islanders",value="islanders:-10",
             resulting_reputation=20,source_frame_digest="a"*64),
    ]
    return {
        "schema":"skeleton.game.native_godot_dispatch.v1","actor_id":"hero",
        "source_through_frame":4,"receipt_digest":"b"*64,"actions":commands,
        "expected_local_xp":110,"expected_local_level":2,
        "expected_unlocked_skills":{"wind_dash":2},
        "expected_faction_reputation":{"islanders":20},
        "expected_progression_events":progression,"expected_faction_events":factions,
    }


class IndependentProgressionAdversarialTests(unittest.TestCase):
    def test_full_progression_reputation_source_passes_deterministically(self):
        proof=audit_native_progression(case())
        self.assertEqual(proof["xp"],110)
        self.assertEqual(proof["level"],2)
        self.assertEqual(proof["unlocked_skills"],{"wind_dash":2})
        self.assertEqual(proof["faction_reputation"],{"islanders":20})
        self.assertEqual(proof,audit_native_progression(case()))

    def test_source_forgery_and_out_of_order_rejected(self):
        for index,key,value in (
            (0,"frame",2),(0,"target","intruder"),(1,"page_id",""),
            (2,"native_frame_receipt_digest","f"*63),
            (4,"frame",-1),(4,"frame",5),
        ):
            d=case()
            d["actions"][index][key]=value
            with self.subTest(index=index,key=key),self.assertRaises(NativeQuestSessionError):
                audit_native_progression(d)

    def test_unsafe_xp_skill_and_faction_values_rejected(self):
        for index,value in (
            (0,"0"),(0,"010"),(0,"１２"),(2,"wind_dash:3"),
            (2,"_admin:2"),(2,"wind/dash:2"),(3,"islanders:25"),
            (3,"islanders:+0"),(4,"islanders:-101"),
        ):
            d=case()
            d["actions"][index]["value"]=value
            with self.subTest(index=index,value=value),self.assertRaises(NativeQuestSessionError):
                audit_native_progression(d)

    def test_forged_compiled_progression_and_reputation_rejected(self):
        for name,value in (
            ("expected_local_xp",200),
            ("expected_local_level",3),
            ("expected_local_level",2.0),
            ("expected_unlocked_skills",{"wind_dash":1}),
            ("expected_faction_reputation",{"islanders":100}),
            ("expected_progression_events",[]),("expected_faction_events",[]),
        ):
            d=case()
            d[name]=value
            with self.subTest(name=name),self.assertRaises(NativeQuestSessionError):
                audit_native_progression(d)

    def test_reordered_skill_before_xp_is_rejected(self):
        d=case()
        d["actions"][2],d["actions"][0]=d["actions"][0],d["actions"][2]
        d["actions"][0]["frame"]=0
        d["actions"][2]["frame"]=2
        with self.assertRaises(NativeQuestSessionError):
            audit_native_progression(d)


class IndependentProgressionIntegrationTests(NativeEngineDispatchTests):
    def test_published_source_compiler_rechecked_against_other_reducer(self):
        d=self.dispatch()
        evidence=audit_native_progression(d)
        self.assertEqual(evidence["xp"],0)
        self.assertEqual(evidence["level"],1)
        self.assertEqual(evidence["approved_commands_reviewed"],6)
