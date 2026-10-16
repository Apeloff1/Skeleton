"""Specialized original-game gameplay branching and empirical Dragon policy tests.

Run: python -m unittest tests.test_jeeves_director_branch_policy
These tests do not assert full native-playthrough or production LLM training.
"""
from __future__ import annotations

import json
import http.client
from http.server import HTTPServer
import threading
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.developer.game_cli import SCHEMA as WORKSPACE_SCHEMA, run_game_cli
from skeleton.developer.jeeves_game_director_session import begin, choose, inspect
from skeleton.developer.jeeves_game_director_branch import fork, trace
from skeleton.developer.jeeves_game_dragon_policy import preview, train, predict
from skeleton.developer.jeeves_game_director_atlas import export, verify
from skeleton.developer.jeeves_game_director_bridge import handler


class BranchAndDragonMicroWeightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "original_game"
        self.root.mkdir()
        (self.root / "design").mkdir()
        (self.root / "skeleton.game.json").write_text(json.dumps({
            "schema": WORKSPACE_SCHEMA, "name": "original_game",
            "vision": "An original world with consequence-driven quests",
            "era": "extraction_now", "archetype": "auto",
        }))
        self.world = forge_director(
            "original_game", seed=71,
            regions=("harbor", "market", "observatory", "garden"),
            quest_types=("main_story", "investigation", "crafting"),
            stages=2,
        )
        self.source = "design/director_campaign_source.json"
        (self.root / self.source).write_text(json.dumps({
            "schema": "skeleton.jeeves.director_campaign_source.v1",
            "author_review_acknowledged": True,
            "director_world": self.world.payload(),
        }))

    def _start(self, name: str) -> dict:
        return begin(self.root, source=self.source, session=name)

    def _act(self, name: str, action: str = "wait:wait") -> dict:
        before = inspect(self.root, session=name)
        return choose(
            self.root, session=name, choice=action,
            expected_sequence=before["sequence"],
            expected_state_sha256=before["current_state_sha256"],
        )

    def test_fork_from_partial_history_preserves_original(self) -> None:
        self._start("hero")
        first = self._act("hero")
        second = self._act("hero")
        parent = inspect(self.root, session="hero")
        self.assertEqual(parent["sequence"], 2)
        lineage = trace(self.root, session="hero", tail=1)
        self.assertEqual(len(lineage["recent_actions"]), 1)
        self.assertEqual(lineage["head_sha256"], parent["last_receipt_sha256"])
        with self.assertRaises(ValueError):
            fork(self.root, session="hero", new_session="variant", at=1,
                 approved_head="0" * 64)
        output = fork(self.root, session="hero", new_session="variant", at=1,
                      approved_head=parent["last_receipt_sha256"])
        self.assertEqual(output["fork_sequence"], 1)
        self.assertEqual(output["state_sha256"], first["current_state_sha256"])
        variant = inspect(self.root, session="variant")
        self.assertEqual(variant["sequence"], 1)
        lineage = trace(self.root, session="variant")
        self.assertEqual(lineage["fork_origin"]["parent_session"], "hero")
        self.assertEqual(lineage["fork_origin"]["parent_head_sha256"],
                         parent["last_receipt_sha256"])
        self.assertEqual(lineage["fork_origin"]["fork_sequence"], 1)
        self.assertNotEqual(variant["last_receipt_sha256"], first["last_receipt_sha256"])
        self.assertEqual(variant["current_state_sha256"], first["current_state_sha256"])
        travel = next(x["choice"] for x in variant["actions"] if x["kind"] == "travel")
        diverted = self._act("variant", travel)
        self.assertEqual(diverted["sequence"], 2)
        self.assertEqual(inspect(self.root, session="hero")["sequence"], 2)
        self.assertEqual(inspect(self.root, session="hero")["current_state_sha256"],
                         second["current_state_sha256"])
        with self.assertRaises(ValueError):
            fork(self.root, session="hero", new_session="variant", at=1,
                 approved_head=parent["last_receipt_sha256"])

    def test_fork_at_genesis_and_branch_source_change(self) -> None:
        self._start("hero")
        self._act("hero")
        parent = inspect(self.root, session="hero")
        output = fork(self.root, session="hero", new_session="opening", at=0,
                      approved_head=parent["last_receipt_sha256"])
        self.assertEqual(output["fork_sequence"], 0)
        self.assertEqual(inspect(self.root, session="opening")["sequence"], 0)
        edited = self.root / self.source
        raw = edited.read_text()
        edited.write_text(raw.replace("Shared hope", "A different promise"))
        with self.assertRaises(ValueError):
            inspect(self.root, session="opening")

    def test_empirical_dragon_model_is_fitted_and_held_out(self) -> None:
        for name in ("train_one", "train_two", "holdout", "new_game"):
            self._start(name)
        self._act("train_one")
        self._act("train_two")
        self._act("holdout")
        names = "train_one,train_two,holdout"
        checked = preview(self.root, sessions=names)
        self.assertTrue(checked["empirical_parameters_fitted"])
        self.assertEqual(checked["model"]["train_action_count"], 2)
        self.assertEqual(checked["model"]["heldout_action_count"], 1)
        self.assertEqual(checked["model"]["heldout_context_coverage_count"], 1)
        self.assertEqual(checked["model"]["heldout_top1_correct_count"], 1)
        self.assertFalse(checked["model"]["foundational_llm_checkpoint_updated"])
        with self.assertRaises(ValueError):
            train(self.root, sessions=names, approved_digest="0" * 64)
        fitted = train(self.root, sessions=names,
                       approved_digest=checked["model_sha256"])
        self.assertTrue(fitted["empirical_parameters_persisted"])
        self.assertTrue(Path(fitted["checkpoint"]).is_file())
        recommendation = predict(self.root, session="new_game",
                                 digest=checked["model_sha256"])
        self.assertFalse(recommendation["abstained"])
        self.assertEqual(recommendation["advisory_choices"][0]["choice"], "wait:wait")
        self.assertFalse(recommendation["gameplay_action_executed"])
        self.assertEqual(inspect(self.root, session="new_game")["sequence"], 0)
        with self.assertRaises(ValueError):
            train(self.root, sessions=names,
                  approved_digest=checked["model_sha256"])

    def test_policy_abstains_on_unseen_quest_state_and_detects_drift(self) -> None:
        for name in ("train_one", "train_two", "holdout", "new_game"):
            self._start(name)
        for name in ("train_one", "train_two", "holdout"):
            self._act(name)
        checked = preview(self.root, sessions="train_one,train_two,holdout")
        train(self.root, sessions="train_one,train_two,holdout",
              approved_digest=checked["model_sha256"])
        current = inspect(self.root, session="new_game")
        travel = next(x["choice"] for x in current["actions"] if x["kind"] == "travel")
        self._act("new_game", travel)
        result = predict(self.root, session="new_game", digest=checked["model_sha256"])
        self.assertTrue(result["abstained"])
        self._act("train_one")
        with self.assertRaises(ValueError):
            predict(self.root, session="new_game", digest=checked["model_sha256"])

    def test_dragon_advice_endpoint_is_opt_in_and_never_executes_actions(self) -> None:
        for name in ("train_one", "train_two", "holdout", "new_game"):
            self._start(name)
        for name in ("train_one", "train_two", "holdout"):
            self._act(name)
        sessions = "train_one,train_two,holdout"
        model = preview(self.root, sessions=sessions)
        train(self.root, sessions=sessions, approved_digest=model["model_sha256"])
        with self.assertRaises(ValueError):
            handler(self.root, "new_game", "x" * 40, 0,
                    policy_digest="0" * 64)
        server = HTTPServer(
            ("127.0.0.1", 0),
            handler(self.root, "new_game", "x" * 40, 0,
                    policy_digest=model["model_sha256"]),
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("GET", "/v1/advice", headers={
                    "Host": "127.0.0.1:" + str(server.server_port),
                    "Authorization": "Bearer " + "x" * 40,
                })
                result = connection.getresponse()
                body = json.loads(result.read())
                self.assertEqual(result.status, 200)
                self.assertTrue(body["advice"]["trained_context_observed"])
                self.assertEqual(body["advice"]["advisory_choices"][0]["choice"],
                                 "wait:wait")
                self.assertEqual(inspect(self.root, session="new_game")["sequence"], 0)
            finally:
                connection.close()
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()

    def test_native_procedural_stage_and_controller_bindings_are_exported(self) -> None:
        result = export(self.root, source=self.source)
        generated = Path(result["path"])
        actor = (generated / "director_stage.gd").read_text()
        player = (generated / "director_player.gd").read_text()
        self.assertIn("enqueue_presentation", actor)
        self.assertIn("func toggle_pause()", actor)
        self.assertIn("func set_playback_speed", actor)
        self.assertIn("camera_pan", actor)
        self.assertIn("JOY_BUTTON_A", player)
        self.assertIn("func _unhandled_input", player)
        self.assertIn("stage.enqueue_presentation", player)
        self.assertIn("/v1/advice", player)
        self.assertIn("Ask Dragon", player)
        self.assertTrue(verify(self.root, source=self.source)["source_manifest_verified"])
        self.assertTrue(result["manifest"]["procedural_2d_stage_in_source"])
        self.assertFalse(result["manifest"]["native_binary_executed"])

    def test_cli_commands_respect_exact_approval_and_no_extraneous_flags(self) -> None:
        self._start("hero")
        self._act("hero")
        response = run_game_cli([
            "jeeves", "director-session-trace", "--project", str(self.root),
            "--session", "hero", "--tail", "1",
        ])
        self.assertTrue(response["ok"])
        response = run_game_cli([
            "jeeves", "director-session-fork", "--project", str(self.root),
            "--session", "hero", "--other-session", "alternative",
            "--at", "0", "--approve", "0" * 64,
        ])
        self.assertFalse(response["ok"])
        response = run_game_cli([
            "jeeves", "dragon-policy-preview", "--project", str(self.root),
            "--sessions", "hero,hero,hero",
        ])
        self.assertFalse(response["ok"])


if __name__ == "__main__":
    unittest.main()
