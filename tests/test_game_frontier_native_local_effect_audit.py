"""Adversarial, independent game-health and consumable reducer tests."""
from copy import deepcopy
import unittest

from skeleton.jeeves.game_frontier_native_local_effect_audit import (
    audit_native_local_effects,
)
from skeleton.jeeves.game_frontier_native_quest_session import NativeQuestSessionError
from tests.test_game_frontier_native_engine_dispatch import NativeEngineDispatchTests


def _source_case():
    actions=[]
    for frame,kind,value in (
        (0,"craft_item","herb"),(0,"craft_item","herb"),
        (1,"take_damage","30"),(2,"heal_health","12"),
        (3,"consume_item","herb"),
    ):
        actions.append({
            "kind":kind,"value":value,"frame":frame,"actor_id":"hero",
            "target":"hero","page_id":"story_event",
            "native_frame_receipt_digest":"a"*64,
        })
    history=[
        {"frame":1,"page_id":"story_event","kind":"take_damage",
         "value":"30","resulting_health":70,"source_frame_digest":"a"*64},
        {"frame":2,"page_id":"story_event","kind":"heal_health",
         "value":"12","resulting_health":82,"source_frame_digest":"a"*64},
        {"frame":3,"page_id":"story_event","kind":"consume_item",
         "value":"herb","resulting_health":82,"source_frame_digest":"a"*64},
    ]
    return {
        "schema":"skeleton.game.native_godot_dispatch.v1",
        "source_through_frame":4,"actor_id":"hero",
        "receipt_digest":"b"*64,
        "actions":actions,
        "expected_local_health":82,
        "expected_inventory":{"herb":1},
        "expected_local_effect_history":history,
    }


class NativeLocalEffectAuditTests(unittest.TestCase):
    def test_independent_local_reducer_health_consumables(self):
        source=_source_case()
        report=audit_native_local_effects(source)
        self.assertEqual(report["health"],82)
        self.assertEqual(report["inventory"],{"herb":1})
        self.assertEqual(report["source_approved_commands_checked"],5)
        self.assertEqual(len(report["effect_history"]),3)
        self.assertEqual(len(report["receipt_digest"]),64)
        self.assertEqual(report,audit_native_local_effects(source))

    def test_mutated_damage_heal_consumption_receipts_fail_closed(self):
        for event_index,key,value in (
            (2,"value","100"),(3,"value","100"),(4,"value","different"),
            (1,"frame",4),(0,"target","intruder"),(0,"page_id",""),
            (1,"native_frame_receipt_digest","bad"),
        ):
            source=_source_case()
            source["actions"][event_index][key]=value
            with self.subTest(index=event_index,key=key,value=value):
                with self.assertRaises(NativeQuestSessionError):
                    audit_native_local_effects(source)

    def test_forged_inventory_health_or_effect_history_rejected(self):
        for key,value in (
            ("expected_inventory",{"herb":2}),
            ("expected_local_health",100),
            ("expected_local_health",82.),
            ("expected_local_effect_history",[]),
        ):
            source=_source_case()
            source[key]=value
            with self.subTest(key=key),self.assertRaises(NativeQuestSessionError):
                audit_native_local_effects(source)

    def test_reject_invalid_health_numbers_and_item_ids(self):
        for value in ("0","00","010","101","-1","1.0","１２","x",""):
            source=_source_case()
            source["actions"][2]["value"]=value
            with self.subTest(value=value),self.assertRaises(NativeQuestSessionError):
                audit_native_local_effects(source)
        for value in ("", "other/item","../save","éclair","a b"):
            source=_source_case()
            source["actions"][0]["value"]=value
            with self.subTest(value=value),self.assertRaises(NativeQuestSessionError):
                audit_native_local_effects(source)

    def test_no_item_consume_before_crafting(self):
        source=_source_case()
        source["actions"][0]["kind"]="consume_item"
        with self.assertRaisesRegex(NativeQuestSessionError,"before award"):
            audit_native_local_effects(source)

    def test_health_clamping_at_zero_and_full_is_defined(self):
        source=_source_case()
        source["actions"]=[
            dict(source["actions"][2],frame=0,value="100"),
            dict(source["actions"][2],frame=1,value="100"),
            dict(source["actions"][3],frame=2,value="100"),
            dict(source["actions"][3],frame=3,value="20"),
        ]
        source["expected_local_health"]=100
        source["expected_inventory"]={}
        source["expected_local_effect_history"]=[
            dict(source["expected_local_effect_history"][0],frame=0,value="100",resulting_health=0),
            dict(source["expected_local_effect_history"][0],frame=1,value="100",resulting_health=0),
            dict(source["expected_local_effect_history"][1],frame=2,value="100",resulting_health=100),
            dict(source["expected_local_effect_history"][1],frame=3,value="20",resulting_health=100),
        ]
        self.assertEqual(audit_native_local_effects(source)["health"],100)


class NativeLocalEffectIntegrationTests(NativeEngineDispatchTests):
    def test_independent_verifier_matches_real_approved_quest_actions(self):
        source=self.dispatch()
        second=audit_native_local_effects(source)
        self.assertEqual(second["source_approved_commands_checked"],6)
        self.assertEqual(second["health"],100)
        self.assertEqual(second["inventory"],{})
