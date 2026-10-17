"""Specialized labyrinth, canonical causality and native route UI regressions.

Run: python -m unittest tests.test_jeeves_director_labyrinth_causality
No global CI job or obligatory merge gate is created.
"""
from __future__ import annotations

import http.client
from http.server import HTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.quest_campaign_completion import play_campaign
from skeleton.developer.game_cli import SCHEMA as GAME_SCHEMA, run_game_cli
from skeleton.developer.jeeves_game_director_session import begin, choose, inspect
from skeleton.developer.jeeves_game_director_labyrinth import plan, topology
from skeleton.developer.jeeves_game_director_causality import audit, contrast
from skeleton.developer.jeeves_game_dragon_navigation import study, queue as navigation_queue
from skeleton.developer.jeeves_game_director_bridge import handler
from skeleton.developer.jeeves_game_director_atlas import export, verify


class LabyrinthCausalityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "original_game"
        self.root.mkdir()
        (self.root / "design").mkdir()
        (self.root / "skeleton.game.json").write_text(json.dumps({
            "schema": GAME_SCHEMA, "name": "original_game",
            "vision": "A strange original living labyrinth with consequences",
            "era": "extraction_now", "archetype": "auto",
        }))
        self.world = forge_director(
            "original_game", seed=29,
            regions=("harbor", "garden", "library", "tower"),
            quest_types=("main_story", "investigation"), stages=2,
        )
        self.source = "design/director_campaign_source.json"
        (self.root / self.source).write_text(json.dumps({
            "schema": "skeleton.jeeves.director_campaign_source.v1",
            "author_review_acknowledged": True,
            "director_world": self.world.payload(),
        }))
        begin(self.root, source=self.source, session="hero")

    def _move(self, session, choice):
        before = inspect(self.root, session=session)
        return choose(self.root, session=session, choice=choice,
                      expected_sequence=before["sequence"],
                      expected_state_sha256=before["current_state_sha256"])

    def test_labyrinth_routes_are_replayed_and_head_bound(self):
        here = inspect(self.root, session="hero")
        target = self.world.scenes[-1].key
        for profile in ("fastest", "scenic", "quiet", "novel", "quest"):
            routes = plan(self.root, session="hero", destination=target,
                          profile=profile, alternatives=3)
            self.assertTrue(routes["ok"])
            self.assertEqual(routes["state_sha256"], here["current_state_sha256"])
            self.assertFalse(routes["gameplay_actions_executed"])
            self.assertFalse(routes["all_possible_labyrinth_paths_enumerated"])
            self.assertGreaterEqual(len(routes["routes"]), 1)
            for suggestion in routes["routes"]:
                self.assertEqual(suggestion["places"][0], here["scene"])
                self.assertEqual(suggestion["places"][-1], target)
                self.assertEqual(len(suggestion["actions"]), suggestion["hops"])
                self.assertTrue(suggestion["canonical_actions_replayed"])
        choice = next(x["choice"] for x in here["actions"] if x["kind"] == "travel")
        self._move("hero", choice)
        changed = plan(self.root, session="hero", destination=target)
        self.assertNotEqual(changed["session_head_sha256"], routes["session_head_sha256"])
        self.assertEqual(changed["session_sequence"], 1)

    def test_quest_route_and_world_topology(self):
        targeted = plan(self.root, session="hero", profile="quest")
        self.assertGreaterEqual(len(targeted["targeted_active_quests"]), 1)
        self.assertTrue(all(x["canonical_actions_replayed"] for x in targeted["routes"]))
        atlas = topology(self.root, source=self.source)
        self.assertEqual(atlas["scene_count"], 4)
        self.assertEqual(len(atlas["scenes"]), 4)
        self.assertFalse(atlas["labyrinth_design_quality_independently_verified"])
        self.assertEqual(atlas["world_sha256"], targeted["world_sha256"])
        self.assertEqual(len(atlas["quest_placement_gaps"]), 0)
        with self.assertRaises(ValueError):
            plan(self.root, session="hero", destination="../other_game")
        with self.assertRaises(ValueError):
            plan(self.root, session="hero", profile="unsupported")
        with self.assertRaises(ValueError):
            plan(self.root, session="hero", alternatives=0)

    def test_exact_quest_causality_and_page_receipts(self):
        witness = play_campaign(self.world, preference=0, include_optional=False)
        for segment in witness.replay["segments"]:
            for action in segment["actions"]:
                self._move("hero", action["kind"] + ":" + action["key"])
        report = audit(self.root, session="hero", page=1, page_size=3)
        summary = report["summary"]
        self.assertTrue(summary["complete_campaign_logic"])
        self.assertEqual(summary["stages_completed"], 4)
        self.assertEqual(summary["quest_completion_count"], 2)
        self.assertEqual(summary["actions_replayed"],
                         witness.report["action_count"])
        self.assertTrue(report["recorded_causal_replay_verified"])
        self.assertFalse(summary["literary_voice_independently_reviewed"])
        self.assertEqual(report["total_events"], witness.report["action_count"])
        self.assertLessEqual(len(report["events"]), 3)
        self.assertEqual(report["events"][0]["sequence"], 1)
        next_page = audit(self.root, session="hero", page=2, page_size=3)
        self.assertEqual(next_page["summary_sha256"], report["summary_sha256"])
        self.assertEqual(next_page["events"][0]["sequence"], 4)
        self.assertTrue(summary["consequence_flags_created_at"])
        with self.assertRaises(ValueError):
            audit(self.root, session="hero", page_size=0)

    def test_dragon_measures_maze_deviation_without_guessing_preferences(self):
        initial = inspect(self.root, session="hero")
        travel = next(x["choice"] for x in initial["actions"] if x["kind"] == "travel")
        traveled = self._move("hero", travel)
        self._move("hero", "wait:wait")
        review = navigation_queue(self.root, session="hero")
        study_result = review["study"]
        self.assertEqual(study_result["actions_verified"], 2)
        self.assertEqual(study_result["travel_hops"], 1)
        self.assertEqual(study_result["interaction_actions"], 0)
        self.assertFalse(study_result["player_exploration_preference_inferred"])
        self.assertEqual(study_result["journal_head_sha256"],
                         inspect(self.root, session="hero")["last_receipt_sha256"])
        self.assertFalse(review["model_weights_updated"])
        with self.assertRaises(ValueError):
            navigation_queue(self.root, session="hero",
                             approved_digest="0" * 64)
        admitted = navigation_queue(self.root, session="hero",
                                    approved_digest=review["study_sha256"])
        self.assertTrue(admitted["admitted_to_research"])
        self.assertTrue(Path(admitted["path"]).is_file())
        with self.assertRaises(ValueError):
            navigation_queue(self.root, session="hero",
                             approved_digest=review["study_sha256"])
        self._move("hero", "wait:wait")
        with self.assertRaises(ValueError):
            navigation_queue(self.root, session="hero",
                             approved_digest=review["study_sha256"])

    def test_compare_story_branches_with_distinct_actions(self):
        begin(self.root, source=self.source, session="alternate")
        self._move("hero", "wait:wait")
        here = inspect(self.root, session="alternate")
        travel = next(x["choice"] for x in here["actions"] if x["kind"] == "travel")
        self._move("alternate", travel)
        diff = contrast(self.root, first="hero", second="alternate")
        self.assertEqual(diff["first_different_action_sequence"], 1)
        self.assertEqual(diff["flags_unique_to_first"], [])
        self.assertFalse(diff["canon_story_differences_observed"])
        self.assertFalse(diff["visual_engine_ending_verified"])

    def test_loopback_navigation_authentication_and_stale_query(self):
        server = HTTPServer(("127.0.0.1", 0), handler(
            self.root, "hero", "s" * 40, 0))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                conn.request("GET", "/v1/navigation?profile=quest&alternatives=2",
                             headers={
                                "Host": "127.0.0.1:" + str(server.server_port),
                                "Authorization": "Bearer " + "s" * 40,
                             })
                response = conn.getresponse()
                body = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertTrue(body["navigation"]["routes"])
                self.assertEqual(inspect(self.root, session="hero")["sequence"], 0)
            finally:
                conn.close()
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()

    def test_generated_native_ui_includes_authoritative_navigation(self):
        exported = export(self.root, source=self.source)
        project = Path(exported["path"])
        native = (project / "director_player.gd").read_text()
        self.assertIn("Find quest route", native)
        self.assertIn("/v1/navigation", native)
        self.assertIn("session_head_sha256", native)
        self.assertIn("Travel first step", native)
        self.assertIn("res://director_minimap.gd", native)
        self.assertIn("native_map.node_selected.connect", native)
        map_source = (project / "director_minimap.gd").read_text()
        self.assertIn("signal node_selected", map_source)
        self.assertIn("selected_path", map_source)
        self.assertIn("graph[name]", map_source)
        self.assertIn("node_selected.emit", map_source)
        self.assertTrue(exported["manifest"]["directed_world_minimap_in_source"])
        self.assertTrue(verify(self.root, source=self.source)["source_manifest_verified"])

    def test_cli_wiring_rejects_irrelevant_options(self):
        good = run_game_cli([
            "jeeves", "director-topology", "--project", str(self.root),
            "--source", self.source,
        ])
        self.assertTrue(good["ok"])
        routes = run_game_cli([
            "jeeves", "director-route", "--project", str(self.root),
            "--session", "hero", "--route-profile", "scenic",
        ])
        self.assertTrue(routes["ok"])
        rejected = run_game_cli([
            "jeeves", "director-route", "--project", str(self.root),
            "--session", "hero", "--kind", "asset",
        ])
        self.assertFalse(rejected["ok"])


if __name__ == "__main__":
    unittest.main()
