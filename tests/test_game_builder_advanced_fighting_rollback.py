"""Proof of original, authoritative two-player rollback fighting execution."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import tempfile
import unittest

from skeleton.ai.game_builder.advanced_fighting_rollback import (
    SCHEMA,MAX_FRAMES,FightingRollbackError,
    run_peer_fight,verify_peer_fight,
    reconcile_peer_prediction,verify_peer_reconciliation,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.system_editors import make_editor_document


class OriginalPeerRollbackTests(unittest.TestCase):
    @staticmethod
    def rules(**overrides):
        return {
            "arena_width":8,"rounds_to_win":2,
            "ai_style":"defensive","ai_defense_frequency":0,
            "hazards_enabled":False,"cover_enabled":False,
            **overrides
        }

    def test_original_two_peer_fighting_is_completely_deterministic_without_scripted_ai(self):
        cfg=self.rules()
        blue=["inspect","approach","approach","guard_high","charge","inspect"]
        red=["approach","inspect","approach","guard_low","recover","inspect"]
        match=run_peer_fight(cfg,blue,red,seed=7)
        self.assertEqual(match["schema"],SCHEMA)
        self.assertEqual(match["frames"],6)
        self.assertEqual(len(match["trace"]),6)
        self.assertEqual(match["trace"][0]["priority"],"blue")
        self.assertEqual(match["trace"][1]["priority"],"red")
        self.assertEqual(match["state"]["turn"],6)
        self.assertTrue(verify_peer_fight(match,cfg))
        self.assertEqual(match,run_peer_fight(cfg,blue,red,seed=7))
        self.assertEqual(match["head_digest"],match["trace"][-1]["digest"])
        self.assertEqual(match["trace"][1]["previous_digest"],
                         match["trace"][0]["digest"])
        self.assertFalse(match["network_transport_certified"])
        self.assertFalse(match["hardware_controller_latency_verified"])
        self.assertFalse(match["untrusted_network_state_accepted"])

    def test_actual_two_human_inputs_can_produce_real_knockout_and_victory(self):
        cfg=self.rules(rounds_to_win=1,enemy_health=10,attack_bonus=10)
        blue=["approach","approach","jab"]
        red=["approach","approach","inspect"]
        match=run_peer_fight(cfg,blue,red)
        self.assertTrue(match["state"]["finished"])
        self.assertTrue(match["state"]["victory"])
        self.assertEqual(match["state"]["red_rounds"],0)
        self.assertEqual(match["state"]["blue_rounds"],1)
        self.assertEqual(match["state"]["reason"],"legitimate_arena_champion")
        self.assertEqual(match["state"]["opponent"]["hp"],0)
        self.assertTrue(verify_peer_fight(match,cfg))
        with self.assertRaises(FightingRollbackError):
            run_peer_fight(cfg,blue+["inspect"],red+["inspect"])

    def test_real_remote_prediction_correction_only_reexecutes_valid_source_actions(self):
        cfg=self.rules(rollback_window_frames=4,max_rollback_corrections=2)
        blue=["inspect"]*6
        prediction=["inspect"]*6
        authenticated=["inspect"]*4+["approach","approach"]
        proof=reconcile_peer_prediction(cfg,blue,prediction,authenticated,seed=4)
        self.assertEqual(proof["reconciled_indices"],[4,5])
        self.assertEqual(proof["rollback_window_frames"],4)
        self.assertFalse(proof["prediction_is_authoritative"])
        self.assertFalse(proof["remote_client_state_trusted"])
        self.assertTrue(verify_peer_reconciliation(proof,cfg))
        correct=run_peer_fight(cfg,blue,authenticated,seed=4)
        self.assertEqual(proof["authoritative_match"],correct)
        self.assertNotEqual(proof["predicted_match_digest"],correct["digest"])
        self.assertEqual(correct["state"]["opponent"]["x"],4)

    def test_actual_parry_is_order_dependent_and_cannot_be_fabricated(self):
        cfg=self.rules(starting_stamina=100)
        blue=["approach","approach","inspect","jab"]
        red=["approach","approach","inspect","parry"]
        match=run_peer_fight(cfg,blue,red)
        self.assertEqual(match["state"]["opponent"]["parried"],1)
        self.assertGreater(match["state"]["player"]["stun"],0)
        self.assertTrue(verify_peer_fight(match,cfg))

    def test_real_signed_arena_ownership_and_exact_settings_custody(self):
        cfg=self.rules()
        scene=make_advanced_scene("fighting",cfg,seed=12)
        match=run_peer_fight(cfg,["approach","guard_high"],
                             ["approach","inspect"],seed=12,scene=scene)
        self.assertTrue(verify_peer_fight(match,cfg))
        self.assertEqual(match["scene_digest"],scene["digest"])
        for mutate in (
            lambda m:m["state"]["player"].update(hp=99999),
            lambda m:m["state"]["opponent"].update(meter=900),
            lambda m:m["trace"][0].update(previous_digest="0"*64),
            lambda m:m["trace"][-1].update(state_digest="1"*64),
            lambda m:m.update(head_digest="f"*64),
            lambda m:m.update(network_transport_certified=True),
            lambda m:m["source"]["layout"].update(weather="pirated_stage"),
            lambda m:m["red_actions"].__setitem__(0,"special"),
        ):
            forged=deepcopy(match);mutate(forged)
            with self.assertRaises((FightingRollbackError,ValueError)):
                verify_peer_fight(forged,cfg)
        with self.assertRaises((FightingRollbackError,ValueError)):
            verify_peer_fight(match,{**cfg,"arena_width":10})

    def test_spoofed_remote_timelines_fail_closed_no_rollback_outside_window(self):
        cfg=self.rules(rollback_window_frames=3)
        actions=["inspect"]*8
        remote=["approach"]+["inspect"]*7
        with self.assertRaises(FightingRollbackError):
            reconcile_peer_prediction(cfg,actions,actions,remote)
        allowed=["inspect"]*7+["approach"]
        self.assertTrue(verify_peer_reconciliation(
            reconcile_peer_prediction(cfg,actions,actions,allowed),cfg))
        locked=self.rules(rollback_compatible=False)
        with self.assertRaises(FightingRollbackError):
            run_peer_fight(locked,[],[])
        with self.assertRaises(FightingRollbackError):
            reconcile_peer_prediction(locked,[],[],[])
        for forbidden in (["teleport:10"],["set_score:999"],["auto_win"],
                          ["attack:0"],["projectile:infinite"]):
            with self.assertRaises(FightingRollbackError):
                run_peer_fight(cfg,forbidden,["inspect"])

    def test_peer_streams_must_be_aligned_and_frame_counts_must_be_bounded(self):
        cfg=self.rules()
        for blue,red in (
            (["inspect"],[]),
            (["inspect"]*129,["inspect"]*129),
            (["inspect",True],["inspect","inspect"]),
            ("inspect",["inspect"]),
            (None,None),
        ):
            with self.assertRaises(FightingRollbackError):
                run_peer_fight(cfg,blue,red)
        with self.assertRaises(FightingRollbackError):
            run_peer_fight(cfg,[],[],seed=True)
        with self.assertRaises(FightingRollbackError):
            verify_peer_fight({"schema":SCHEMA},cfg)
        empty=run_peer_fight(cfg)
        self.assertTrue(verify_peer_fight(empty,cfg))
        self.assertEqual(empty["frames"],0)

    def test_unauthorized_out_of_budget_late_input_corrections_are_rejected(self):
        cfg=self.rules(rollback_window_frames=6,max_rollback_corrections=1)
        blue=["inspect"]*5
        predicted=["inspect"]*5
        received=["inspect"]*3+["approach","approach"]
        with self.assertRaises(FightingRollbackError):
            reconcile_peer_prediction(cfg,blue,predicted,received)
        good=["inspect"]*4+["approach"]
        signed=reconcile_peer_prediction(cfg,blue,predicted,good)
        forged=deepcopy(signed)
        forged["reconciled_indices"]=[]
        with self.assertRaises(FightingRollbackError):
            verify_peer_reconciliation(forged,cfg)
        forged=deepcopy(signed)
        forged["authoritative_match"]["state"]["victory"]=True
        with self.assertRaises(FightingRollbackError):
            verify_peer_reconciliation(forged,cfg)

    def test_non_native_original_multiplayer_source_is_export_agnostic(self):
        cfg=self.rules()
        pair=run_peer_fight(cfg,["charge","inspect"],["inspect","charge"])
        self.assertTrue(verify_peer_fight(pair,cfg))
        self.assertFalse(pair["network_transport_certified"])
        self.assertFalse(pair["live_peer_identity_certified"])
        self.assertFalse(pair["hardware_controller_latency_verified"])
        self.assertFalse(pair["untrusted_network_state_accepted"])
        self.assertEqual(pair["peer_mode"],
                         "two_authoritative_players_not_scripted_ai")


if __name__=="__main__":
    unittest.main()
