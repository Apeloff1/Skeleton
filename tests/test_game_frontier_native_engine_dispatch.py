"""In-engine quest dispatch only includes approved, independently replayed actions."""
from copy import deepcopy
import unittest

from tests.test_game_frontier_native_quest_batch import NativeQuestBatchTests
from skeleton.jeeves.game_frontier_native_engine_dispatch import (
    compile_native_godot_dispatch, verify_native_godot_dispatch,
    canonical_dispatch_json,dispatch_file_sha256,
)
from skeleton.jeeves.game_frontier_native_quest_session import NativeQuestSessionError


class NativeEngineDispatchTests(NativeQuestBatchTests):
    def dispatch(self,approved=None,checkpoint=None):
        approved=approved if approved is not None else self.approved
        checkpoint=checkpoint or self.replay()["head_checkpoint"]
        return compile_native_godot_dispatch(
            self.journal,self.pages,self.graph,approved,checkpoint,
            actor_id="hero",scene_candidate_digest="d"*64)

    def test_real_source_dispatch_has_only_approved_actions(self):
        data=self.dispatch()
        self.assertEqual(data["source_through_frame"],4)
        self.assertEqual(len(data["actions"]),6)
        self.assertEqual([a["kind"] for a in data["actions"]],
                         ["start_quest","set_flag","advance_quest",
                          "set_flag","advance_quest","show_dialogue"])
        self.assertEqual(data["expected_quests"]["chapter_1"]["stage"],"ending")
        self.assertEqual(data["expected_flags"]["door_open"],True)
        self.assertEqual(data["expected_inventory"],{})
        self.assertEqual(data["expected_npc_emotions"],{})
        self.assertEqual(data["quest_edges"]["chapter_1"]["start"],
                         ["middle","alternate"])
        self.assertEqual(len(dispatch_file_sha256(data)),64)
        self.assertTrue(canonical_dispatch_json(data).endswith("\n"))
        self.assertTrue(verify_native_godot_dispatch(
            self.journal,self.pages,self.graph,self.approved,
            self.replay()["head_checkpoint"],data,
            actor_id="hero",scene_candidate_digest="d"*64))

    def test_unapproved_pages_cannot_become_engine_commands(self):
        manifest=self.fixture.approval(authorized=())
        from skeleton.jeeves.game_frontier_native_quest_batch import replay_native_quest_batches
        checkpoint=replay_native_quest_batches(
            self.journal,self.pages,self.graph,manifest,actor_id="hero",
            scene_candidate_digest="d"*64)["head_checkpoint"]
        dispatch=self.dispatch(approved=manifest,checkpoint=checkpoint)
        self.assertEqual(dispatch["actions"],[])
        self.assertEqual(dispatch["expected_quests"],{})

    def test_forged_state_command_and_source_cannot_be_exported(self):
        data=self.dispatch()
        modified=deepcopy(data)
        modified["actions"][0]["value"]="illicit_gold"
        with self.assertRaises(NativeQuestSessionError):
            verify_native_godot_dispatch(
                self.journal,self.pages,self.graph,self.approved,
                self.replay()["head_checkpoint"],modified,
                actor_id="hero",scene_candidate_digest="d"*64)
        broken=deepcopy(self.replay()["head_checkpoint"])
        broken["flags"]["free_loot"]=True
        with self.assertRaises(NativeQuestSessionError):
            self.dispatch(checkpoint=broken)
        with self.assertRaises(NativeQuestSessionError):
            canonical_dispatch_json(modified)
