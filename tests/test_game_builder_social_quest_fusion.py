"""Original social quest fusion: full gameplay, moving witnesses, source replay."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.advanced_social_quest_fusion import (
    SCHEMA, FAMILIES, BRIDGE_ACTIONS, SocialFusionError,
    run_social_quest_fusion, verify_social_quest_fusion,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.system_editor_cli import main as cli
from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.game_workspace_server import create_workspace_server
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html

SOURCE_EVENT = [
    "quest_director:south", "quest_director:east",
    "quest_director:collect:0",
]
REAL_INTERVIEW = SOURCE_EVENT + ["bridge:interview:0"]
REAL_PLEDGE = REAL_INTERVIEW + ["bridge:pledge:0"]
QUEST_COMPLETION = REAL_PLEDGE + [
    *["quest_director:help:0"] * 5, "quest_director:resolve:0",
]
SOCIAL_CONSENSUS = QUEST_COMPLETION + [
    "dialogue:travel:1", "dialogue:speak:4",
    "dialogue:travel:2", "dialogue:compare:0",
    "dialogue:claim", "bridge:conclude:0",
]


class SocialQuestFusionTests(unittest.TestCase):
    def test_all_three_game_engines_actually_execute_earned_multisource_outcome(self):
        report = run_social_quest_fusion(SOCIAL_CONSENSUS)
        self.assertEqual(report["schema"], SCHEMA)
        self.assertTrue(verify_social_quest_fusion(report))
        self.assertEqual(report["triple_corroborated_interviews"], 1)
        self.assertEqual(report["financed_social_pledges"], 1)
        self.assertEqual(report["earned_narrative_resolutions"], 1)
        self.assertEqual(len(report["narrative_links"]), 3)
        self.assertFalse(report["any_narrative_terminal"])
        self.assertFalse(report["model_weights_promoted"])
        self.assertFalse(report["native_coupled_engine_certified"])
        self.assertFalse(report["release_approved"])
        self.assertTrue(report["distinct_world_coordinates"])
        states = {name: report["worlds"][name]["state"] for name in FAMILIES}
        self.assertTrue(states["dialogue"]["checkpoint"])
        self.assertEqual(states["dialogue"]["corroborations"], [0])
        self.assertEqual(states["dialogue"]["speakers"][0]["supported"], 1)
        self.assertEqual(states["npc_society"]["focus"], 0)
        self.assertTrue(any(m["kind"] == "conversation" and m["resident"] == 0
                            for m in states["npc_society"]["memories"]))
        self.assertTrue(any(m["kind"] == "assistance" and m["resident"] == 0
                            for m in states["npc_society"]["memories"]))
        self.assertGreater(states["npc_society"]["residents"][0]["bond"], 0)
        quest = states["quest_director"]["quests"][0]
        self.assertEqual(quest["ending"], "restored")
        self.assertEqual(quest["status"], "resolved")
        self.assertIn(0, quest["testimonies"])
        self.assertGreaterEqual(quest["material_actions"], 5)
        self.assertEqual(states["quest_director"]["quests_completed"], 1)
        self.assertEqual(report["narrative_links"][0]["physical_event_kind"], "discover")
        self.assertEqual(report["narrative_links"][0]["source_inference"],
                         "three_role_context_not_single_spatial_actor")
        for name in FAMILIES:
            source = run_advanced_session(
                name, report["settings"][name],
                report["worlds"][name]["actions"],
                seed=report["seed"], scene=report["scenes"][name],
            )
            self.assertTrue(verify_advanced_session(source, report["settings"][name]))
            self.assertEqual(source["digest"],
                             report["worlds"][name]["source_session_digest"])
            self.assertEqual(source["state"], report["worlds"][name]["state"])

    def test_partial_games_are_meaningful_and_do_not_auto_award_quests(self):
        for commands, goals in (
            ([], (0, 0, 0)), (SOURCE_EVENT, (0, 0, 0)),
            (REAL_INTERVIEW, (1, 0, 0)),
            (REAL_PLEDGE, (1, 1, 0)),
            (QUEST_COMPLETION, (1, 1, 0)),
        ):
            with self.subTest(commands=commands):
                record = run_social_quest_fusion(commands)
                self.assertTrue(verify_social_quest_fusion(record))
                self.assertEqual((
                    record["triple_corroborated_interviews"],
                    record["financed_social_pledges"],
                    record["earned_narrative_resolutions"],
                ), goals)
                self.assertFalse(record["any_narrative_terminal"])
        before = run_social_quest_fusion(SOURCE_EVENT)
        self.assertEqual(before["worlds"]["dialogue"]["state"]["direct_statements"], [])
        self.assertEqual(before["worlds"]["npc_society"]["state"]["memories"], [])
        self.assertEqual(before["worlds"]["quest_director"]["state"]["quests"][0]["testimonies"], [])

    def test_scheduled_moving_resident_requires_real_paid_pursuit(self):
        record = run_social_quest_fusion(REAL_PLEDGE)
        actions = record["worlds"]["npc_society"]["actions"]
        self.assertGreaterEqual(actions.count("north"), 1)
        self.assertIn("talk", actions)
        self.assertIn("help", actions)
        self.assertLess(record["worlds"]["npc_society"]["state"]["player_energy"],
                        record["settings"]["npc_society"]["player_energy"])
        self.assertLess(record["worlds"]["dialogue"]["state"]["influence"],
                        record["settings"]["dialogue"]["starting_influence"])
        self.assertEqual(record["worlds"]["quest_director"]["state"]["quests"][0]["choice"],
                         "support")

    def test_forbid_omniscient_quasi_witness_phantom_social_rewards_and_remote_links(self):
        missing = (
            ["bridge:interview:0"],
            SOURCE_EVENT + ["bridge:pledge:0"],
            SOURCE_EVENT + ["bridge:conclude:0"],
            ["dialogue:speak:0", *SOURCE_EVENT, "bridge:interview:0"],
            SOURCE_EVENT + ["quest_director:west", "bridge:interview:0"],
            REAL_INTERVIEW + ["bridge:interview:0"],
            REAL_INTERVIEW + ["bridge:conclude:0"],
            REAL_PLEDGE + ["bridge:pledge:0"],
            REAL_PLEDGE + ["bridge:conclude:0"],
            REAL_PLEDGE + ["quest_director:resolve:0"],
            REAL_INTERVIEW + ["dialogue:speak:4"],
            SOURCE_EVENT + ["bridge:interview:3"],
            ["quest_director:collect:0"],
            ["society:talk"],
        )
        for actions in missing:
            with self.subTest(actions=actions):
                with self.assertRaises((SocialFusionError, ValueError)):
                    run_social_quest_fusion(actions)

    def test_no_forged_bridge_action_batch_or_source_ledger_can_be_imported(self):
        report = run_social_quest_fusion(QUEST_COMPLETION)
        attacks = (
            lambda r: r["worlds"]["quest_director"]["state"].__setitem__("gold", 99999),
            lambda r: r["worlds"]["dialogue"]["state"].__setitem__("checkpoint", True),
            lambda r: r["worlds"]["npc_society"]["state"]["residents"][0].__setitem__("bond", 99),
            lambda r: r["narrative_links"][0].__setitem__("physical_event", 5),
            lambda r: r["bindings"][0].__setitem__("quest_site", 3),
            lambda r: r["narrative_links"][0]["quest_firsthand_memory"].__setitem__("source", "rumor"),
            lambda r: r["narrative_links"][1].__setitem__("finite_civic_food_paid", 0),
            lambda r: r.__setitem__("earned_narrative_resolutions", 50),
            lambda r: r.__setitem__("model_weights_promoted", True),
            lambda r: r["journal"][2].__setitem__("command", "quest_director:harm:0"),
            lambda r: r["source_identities"]["dialogue"].__setitem__("scene_digest", "0"*64),
            lambda r: r.__setitem__("digest", "0"*64),
        )
        for attack in attacks:
            forged = deepcopy(report)
            attack(forged)
            with self.subTest(attack=attack):
                with self.assertRaises(SocialFusionError):
                    verify_social_quest_fusion(forged)

    def test_reviewing_a_receipt_cannot_poison_authoritative_role_definitions(self):
        clean = run_social_quest_fusion(REAL_INTERVIEW)
        inspected = deepcopy(clean)
        inspected["bindings"][0]["quest_site"] = 3
        with self.assertRaises(SocialFusionError):
            verify_social_quest_fusion(inspected)
        from skeleton.ai.game_builder.advanced_social_quest_fusion import ROLE_BINDINGS
        self.assertEqual(ROLE_BINDINGS[0]["quest_site"], 0)
        self.assertEqual(ROLE_BINDINGS[0]["dialogue_topic"], 0)
        self.assertTrue(verify_social_quest_fusion(
            run_social_quest_fusion(REAL_INTERVIEW)
        ))

    def test_external_source_scene_and_budget_constraints_fail_closed(self):
        for malformed in (None, "fake", {"nonexistent": {}}, {"dialogue": []}):
            if malformed is None:
                continue
            with self.subTest(malformed=malformed):
                with self.assertRaises((SocialFusionError, ValueError)):
                    run_social_quest_fusion([], settings=malformed)
        for bad in (
            {"seed": -1}, {"seed": True}, {"seed": 2**31},
            {"commands": ["quest_director:wait"] * 65},
            {"commands": ["bridge:interview:00"]},
            {"commands": [False]}, {"commands": ["quest_director:teleport"]},
        ):
            kwargs = {"commands": []}
            kwargs.update(bad)
            with self.subTest(bad=bad):
                with self.assertRaises(SocialFusionError):
                    run_social_quest_fusion(**kwargs)
        source = {name: make_advanced_scene(name) for name in FAMILIES}
        valid = run_social_quest_fusion(SOURCE_EVENT, scenes=source)
        self.assertTrue(verify_social_quest_fusion(valid))
        forged = deepcopy(source)
        forged["quest_director"]["layout"]["player_spawn"] = 8
        with self.assertRaises((SocialFusionError, ValueError)):
            run_social_quest_fusion([], scenes=forged)
        different_seed = deepcopy(source)
        different_seed["dialogue"] = make_advanced_scene("dialogue", seed=1)
        with self.assertRaises(SocialFusionError):
            run_social_quest_fusion([], scenes=different_seed)

    def test_adversarial_memory_and_proximity_settings_never_create_a_false_link(self):
        short = {"quest_director": {"memory_records": 1}}
        altered = run_social_quest_fusion(SOURCE_EVENT, short)
        self.assertEqual(altered["triple_corroborated_interviews"], 0)
        self.assertTrue(verify_social_quest_fusion(altered))
        dialogue = {"dialogue": {"speakers": 1, "active_speakers_budget": 1}}
        with self.assertRaises(SocialFusionError):
            run_social_quest_fusion(SOCIAL_CONSENSUS, dialogue)
        sparse = {"npc_society": {"active_npcs": 0}}
        with self.assertRaises((SocialFusionError, ValueError)):
            run_social_quest_fusion(REAL_INTERVIEW, sparse)


class SocialQuestFusionSurfaces(unittest.TestCase):
    def test_offline_cli_replays_exact_narrative_custody(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            steps = path / "steps.json"
            record = path / "proof.json"
            steps.write_text(json.dumps(SOCIAL_CONSENSUS), encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["social-quest-fusion", "--commands",
                                      str(steps)]), 0)
            data = json.loads(output.getvalue())
            self.assertEqual(data["earned_narrative_resolutions"], 1)
            record.write_text(json.dumps(data), encoding="utf-8")
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(cli(["verify-social-quest-fusion", "--record",
                                      str(record)]), 0)
            self.assertEqual(json.loads(output.getvalue()), {"verified": True})
            data["narrative_links"][-1]["composite_nonterminal_milestone"] = False
            record.write_text(json.dumps(data), encoding="utf-8")
            with redirect_stderr(StringIO()):
                self.assertEqual(cli(["verify-social-quest-fusion", "--record",
                                      str(record)]), 2)

    def test_local_studio_requires_token_and_verifies_before_read_only_review(self):
        with tempfile.TemporaryDirectory() as temp:
            ws = GameWorkspace.create(Path(temp) / "studio", authorized=True)
            ws.create_project("original_shared_story", "hybrid", authorized=True)
            server = create_workspace_server(ws, port=0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            def post(path, body, auth=True):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=8)
                headers = {"Content-Type": "application/json"}
                if auth:
                    headers["X-Game-Studio-Token"] = server.secret
                conn.request("POST", path, json.dumps(body), headers)
                res = conn.getresponse()
                status, content = res.status, json.loads(res.read())
                conn.close()
                return status, content
            try:
                self.assertEqual(post("/api/social-quest-fusion",
                                      {"commands": REAL_INTERVIEW}, False)[0], 403)
                status, content = post("/api/social-quest-fusion",
                                       {"commands": REAL_INTERVIEW})
                self.assertEqual(status, 200)
                self.assertTrue(content["independently_verified"])
                self.assertFalse(content["source_projects_mutated"])
                self.assertEqual(content["record"]["triple_corroborated_interviews"], 1)
                status, check = post("/api/social-quest-fusion-verify",
                                     {"record": content["record"]})
                self.assertEqual(status, 200)
                self.assertTrue(check["verified"])
                forged = deepcopy(content["record"])
                forged["worlds"]["quest_director"]["state"]["gold"] += 1
                self.assertEqual(post("/api/social-quest-fusion-verify",
                                      {"record": forged})[0], 400)
                page = render_workspace_html("x"*32).decode()
                self.assertIn("Original Story Fusion", page)
                self.assertIn("/api/social-quest-fusion", page)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
