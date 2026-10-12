"""Real 20-floor / 200-floor original campaigns and untrusted save rejection."""
from __future__ import annotations

from copy import deepcopy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from skeleton.ai.game_builder.advanced_roguelike_longrun import (
    SCHEMA,MAX_COMMANDS,RoguelikeLongrunError,
    replay_long_roguelike,verify_long_roguelike,continue_long_roguelike,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError,run_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.system_editors import make_editor_document


class OriginalMarathonDungeonTests(unittest.TestCase):
    @staticmethod
    def settings(floors=20):
        return {
          "floors":floors,"encounters_per_floor":1,
          "foe_health":1,"foe_health_growth":0,"health_variance":1,
          "foe_attack":0,"boss_health":1,"boss_health_growth":0,
          "boss_attack":1,"boss_armor":0,"enemy_patrol":False,
          "trap_damage":0,"attack_power":16,"starting_health":100,
        }

    @staticmethod
    def route(floors):
        floor=["move_east"]*4+["strike_east","move_east"]+(
             ["move_south"]*5)
        actions=[]
        for i in range(floors):
            actions.extend(floor)
            if i==floors-1:
                actions.append("strike_west")
            actions.append("take_stairs")
        return actions

    def test_twenty_original_floors_across_four_real_authenticated_checkpoints(self):
        cfg=self.settings()
        actions=self.route(20)
        self.assertGreater(len(actions),128)
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("roguelike",cfg,actions)
        record=replay_long_roguelike(cfg,actions,checkpoint_interval=64)
        self.assertEqual(record["schema"],SCHEMA)
        self.assertEqual(record["turn_count"],len(actions))
        self.assertEqual(record["state"]["floor"],20)
        self.assertTrue(record["state"]["victory"])
        self.assertEqual(record["state"]["total_kills"],21)
        self.assertTrue(record["terminal"])
        self.assertEqual(record["checkpoint_count"],4)
        self.assertTrue(verify_long_roguelike(record,cfg))
        self.assertEqual(record,replay_long_roguelike(
                         cfg,actions,checkpoint_interval=64))
        self.assertFalse(record["native_engine_certified"])
        self.assertFalse(record["hardware_execution_verified"])
        self.assertFalse(record["unverified_checkpoint_state_accepted"])
        self.assertEqual(record["checkpoints"][0]["prior_digest"],
                         record["genesis_digest"])
        for i in range(1,record["checkpoint_count"]):
            self.assertEqual(record["checkpoints"][i]["prior_digest"],
                             record["checkpoints"][i-1]["digest"])
        self.assertEqual(record["head_digest"],record["checkpoints"][-1]["digest"])

    def test_full_original_200_floor_authoring_limit_can_reach_real_final_boss(self):
        cfg=self.settings(200)
        record=replay_long_roguelike(cfg,self.route(200),checkpoint_interval=128)
        self.assertEqual(record["state"]["floor"],200)
        self.assertTrue(record["victory"])
        self.assertEqual(record["state"]["total_kills"],201)
        self.assertGreater(record["checkpoint_count"],15)
        self.assertLessEqual(record["turn_count"],MAX_COMMANDS)
        self.assertTrue(verify_long_roguelike(record,cfg))

    def test_record_custody_rejects_edited_checkpoint_state_and_actions(self):
        cfg=self.settings(3)
        scene=make_advanced_scene("roguelike",cfg,seed=0)
        receipt=replay_long_roguelike(cfg,self.route(3),scene=scene,
                                      checkpoint_interval=8)
        self.assertTrue(verify_long_roguelike(receipt,cfg))
        for mutate in (
            lambda r:r["state"].update(gold=900000),
            lambda r:r["state"].update(victory=False),
            lambda r:r["checkpoints"][0].update(prior_digest="f"*64),
            lambda r:r["checkpoints"][-1].update(state_digest="0"*64),
            lambda r:r["actions"].append("bank_relic"),
            lambda r:r.update(scene_digest="0"*64),
            lambda r:r["scene"]["layout"].update(exit=0),
            lambda r:r.update(checkpoint_interval=4),
            lambda r:r.update(head_digest="a"*64),
            lambda r:r.update(native_engine_certified=True),
        ):
            modified=deepcopy(receipt);mutate(modified)
            with self.assertRaises((RoguelikeLongrunError,ValueError)):
                verify_long_roguelike(modified,cfg)
        with self.assertRaises((RoguelikeLongrunError,ValueError)):
            verify_long_roguelike(receipt,self.settings(2))

    def test_resume_reconstructs_real_prior_world_and_never_trusts_client_checkpoint(self):
        cfg=self.settings(20)
        actions=self.route(20)
        first=replay_long_roguelike(cfg,actions[:120],
                                   checkpoint_interval=16)
        self.assertFalse(first["terminal"])
        self.assertTrue(verify_long_roguelike(first,cfg))
        second=continue_long_roguelike(first,actions[120:],cfg)
        direct=replay_long_roguelike(cfg,actions,
                                    checkpoint_interval=16)
        self.assertEqual(second,direct)
        self.assertTrue(second["victory"])
        with self.assertRaises(RoguelikeLongrunError):
            continue_long_roguelike(second,["inspect"],cfg)
        with self.assertRaises(RoguelikeLongrunError):
            continue_long_roguelike(first,["force_victory"],cfg)
        spoofed=deepcopy(first)
        spoofed["state"]["relics"]=100
        with self.assertRaises(RoguelikeLongrunError):
            continue_long_roguelike(spoofed,actions[120:],cfg)

    def test_bounded_untrusted_inputs_prohibit_unregistered_actions_and_overlong_sessions(self):
        cfg=self.settings()
        for value in (0,1,7,True,129):
            with self.assertRaises(RoguelikeLongrunError):
                replay_long_roguelike(cfg,[],checkpoint_interval=value)
        for actions in (["teleport:35"],["take_stairs"]*MAX_COMMANDS,
                        ["inspect"]*(MAX_COMMANDS+1),"not a list",None):
            with self.assertRaises(RoguelikeLongrunError):
                replay_long_roguelike(cfg,actions)
        with self.assertRaises(RoguelikeLongrunError):
            replay_long_roguelike(cfg,[],seed=True)
        with self.assertRaises(RoguelikeLongrunError):
            verify_long_roguelike({"schema":SCHEMA})
        empty=replay_long_roguelike(cfg,[])
        self.assertTrue(verify_long_roguelike(empty,cfg))
        self.assertEqual(empty["head_digest"],empty["genesis_digest"])


    def test_local_studio_exposes_longrun_replay_without_native_or_file_write_promotion(self):
        from skeleton.ai.game_builder.game_workspace_ui import (
            render_workspace_html,SCRIPT,
        )
        page=render_workspace_html("A"*32).decode("utf-8")
        for token in ("roguelike-longrun-actions","roguelike-longrun-submit",
                      "roguelike-longrun-proof","/api/roguelike-marathon",
                      "originalRoguelikeLongrunRecord",
                      "independently_verified","native_executable_certified"):
            self.assertIn(token,page)
        self.assertIn("originalRoguelikeLongrunRecord=null",SCRIPT)
        self.assertIn("Long-run dungeon replayed from original source",SCRIPT)

    def test_cli_longrun_supports_trusted_replay_and_separate_save_continuation(self):
        from skeleton.ai.game_builder.system_editor_cli import main
        cfg=self.settings(2);actions=self.route(2)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);settings_path=root/"settings.json"
            actions_path=root/"actions.json"
            record_path=root/"record.json"
            settings_path.write_text(json.dumps(cfg),encoding="utf-8")
            actions_path.write_text(json.dumps(actions),encoding="utf-8")
            out=io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["roguelike-marathon",
                    "--actions",str(actions_path),"--settings",
                    str(settings_path),"--checkpoint-interval","8"]),0)
            record=json.loads(out.getvalue())
            self.assertTrue(record["victory"])
            record_path.write_text(json.dumps(record),encoding="utf-8")
            out=io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["roguelike-marathon-verify",
                    "--record",str(record_path),"--settings",
                    str(settings_path)]),0)
            self.assertEqual(json.loads(out.getvalue())["verified"],True)


if __name__=="__main__":
    unittest.main()
