"""Specialized Director interactive runtime + Godot atlas + Dragon intake tests.

Run: python -m unittest tests.test_jeeves_director_interactive
No global CI workflow added.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.developer.game_cli import SCHEMA as WORKSPACE_SCHEMA, run_game_cli
from skeleton.developer.jeeves_game_director_session import (
    begin, inspect, choose, compare,
)
from skeleton.developer.jeeves_game_director_atlas import (
    export, verify,
)
from skeleton.developer.jeeves_game_dragon_session import enqueue
from skeleton.developer.jeeves_game_director_bindings import preview, publish, check


class DirectorInteractiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "original_game"
        self.root.mkdir()
        (self.root / "design").mkdir()
        (self.root / "skeleton.game.json").write_text(json.dumps({
            "schema": WORKSPACE_SCHEMA,
            "name": "original_game",
            "vision": "A new, original exploration title",
            "era": "extraction_now", "archetype": "auto",
        }))
        self.world = forge_director(
            "original_game", seed=13,
            regions=("harbor", "market", "tower", "ruins"),
            quest_types=("main_story", "investigation"), stages=2,
        )
        self.source = "design/director_campaign_source.json"
        (self.root / self.source).write_text(json.dumps({
            "schema": "skeleton.jeeves.director_campaign_source.v1",
            "author_review_acknowledged": True,
            "director_world": self.world.payload(),
        }))

    def test_session_records_actual_wait_and_legal_travel(self):
        first = begin(self.root, source=self.source, session="solo")
        self.assertEqual(first["sequence"], 0)
        self.assertIn("wait:wait", [x["choice"] for x in first["actions"]])
        stepped = choose(self.root, session="solo", choice="wait:wait")
        self.assertEqual(stepped["turn"], 1)
        self.assertEqual(stepped["sequence"], 1)
        self.assertTrue(stepped["actual_interactive_director_logic_executed"])
        self.assertEqual(inspect(self.root, session="solo")["current_state_sha256"],
                         stepped["current_state_sha256"])
        next_travel = next(x for x in stepped["actions"] if x["kind"] == "travel")
        traveled = choose(self.root, session="solo", choice=next_travel["choice"])
        self.assertEqual(traveled["scene"], next_travel["key"])
        self.assertEqual(traveled["sequence"], 2)
        self.assertEqual(len(list((self.root / ".jeeves" / "director_sessions" /
                                   "solo").glob("*.json"))), 3)
        with self.assertRaises(ValueError):
            choose(self.root, session="solo", choice="use:does_not_exist")

    def test_tampering_and_source_drift_fail(self):
        begin(self.root, source=self.source, session="solo")
        choose(self.root, session="solo", choice="wait:wait")
        folder = self.root / ".jeeves" / "director_sessions" / "solo"
        entry = folder / "00000001.json"
        doc = json.loads(entry.read_text())
        doc["after_sha256"] = "0" * 64
        entry.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):
            inspect(self.root, session="solo")
        begin(self.root, source=self.source, session="other")
        raw = self.root / self.source
        raw.write_text(raw.read_text().replace("Shared hope", "Shared ambition"))
        with self.assertRaises(ValueError):
            inspect(self.root, session="other")

    def test_cannot_bypass_lock_or_copy_foreign_session(self):
        begin(self.root, source=self.source, session="solo")
        folder = self.root / ".jeeves" / "director_sessions" / "solo"
        (folder / ".lock").write_text("busy")
        with self.assertRaises(ValueError):
            choose(self.root, session="solo", choice="wait:wait")
        (folder / ".lock").unlink()
        with self.assertRaises(ValueError):
            begin(self.root, source=self.source, session="solo")
        with self.assertRaises(ValueError):
            begin(self.root, source=self.source, session="../escape")

    def test_sessions_compare_without_invented_preferences(self):
        begin(self.root, source=self.source, session="alpha")
        begin(self.root, source=self.source, session="beta")
        choose(self.root, session="alpha", choice="wait:wait")
        result = compare(self.root, first="alpha", second="beta")
        self.assertEqual(result["first_actions"], 1)
        self.assertFalse(result["material_divergence"])
        self.assertFalse(result["real_playtest_or_player_preference_inferred"])

    def test_dragon_session_lesson_is_replay_bound(self):
        begin(self.root, source=self.source, session="alpha")
        choose(self.root, session="alpha", choice="wait:wait")
        preview = enqueue(self.root, session="alpha")
        self.assertFalse(preview["admitted_to_research_queue"])
        self.assertFalse(preview["candidate"]["model_training_started"])
        self.assertEqual(preview["candidate"]["verified_action_count"], 1)
        self.assertFalse(preview["candidate"]["player_preferences_measured"])
        with self.assertRaises(ValueError):
            enqueue(self.root, session="alpha", approved_digest="0" * 64)
        stored = enqueue(self.root, session="alpha",
                         approved_digest=preview["candidate_sha256"])
        self.assertTrue(stored["admitted_to_research_queue"])
        with self.assertRaises(ValueError):
            enqueue(self.root, session="alpha",
                    approved_digest=preview["candidate_sha256"])
        choose(self.root, session="alpha", choice="wait:wait")
        with self.assertRaises(ValueError):
            enqueue(self.root, session="alpha",
                    approved_digest=preview["candidate_sha256"])

    def test_godot_preview_source_integrity(self):
        inspect_result = export(self.root, source=self.source, dry_run=True)
        self.assertTrue(inspect_result["dry_run"])
        self.assertFalse(Path(inspect_result["path"]).exists())
        result = export(self.root, source=self.source)
        self.assertEqual(result["manifest"]["scope"], "interactive-scene-atlas-only")
        self.assertFalse(result["manifest"]["native_binary_executed"])
        self.assertTrue(verify(self.root, source=self.source)["source_manifest_verified"])
        path = Path(result["path"])
        self.assertTrue((path / "project.godot").is_file())
        self.assertTrue((path / "main.tscn").is_file())
        self.assertTrue((path / "director_world.json").is_file())
        with self.assertRaises(ValueError):
            export(self.root, source=self.source)
        (path / "director_atlas.gd").write_text("tampered")
        with self.assertRaises(ValueError):
            verify(self.root, source=self.source)

    def test_engine_controller_binding_contracts_are_pinned_to_original_world(self):
        packet = preview(self.root, source=self.source)
        self.assertEqual(packet["bindings"]["scene_count"], 4)
        self.assertFalse(packet["persisted"])
        self.assertFalse(packet["bindings"]["runtime_ui_wired_to_director"])
        scene = packet["bindings"]["scene_bindings"][0]
        self.assertIn("travel", {x["action"]["kind"] for x in scene["transitions"]})
        with self.assertRaises(ValueError):
            publish(self.root, source=self.source, approved_digest="0" * 64)
        admitted = publish(self.root, source=self.source,
                           approved_digest=packet["candidate_sha256"])
        self.assertFalse(admitted["native_gameplay_verified"])
        self.assertTrue(check(self.root, source=self.source,
                              digest=packet["candidate_sha256"])["binding_source_verified"])
        with self.assertRaises(ValueError):
            publish(self.root, source=self.source,
                    approved_digest=packet["candidate_sha256"])
        original = self.root / self.source
        data = json.loads(original.read_text())
        data["director_world"]["scenes"][0]["setting"] = "A different original setting"
        original.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            check(self.root, source=self.source, digest=packet["candidate_sha256"])

    def test_game_cli_routes_new_actions_and_rejects_unrelated_flags(self):
        response = run_game_cli([
            "jeeves", "director-session-begin", "--project", str(self.root),
            "--source", self.source, "--session", "cli",
        ])
        self.assertTrue(response["ok"])
        status = run_game_cli([
            "jeeves", "director-session-status", "--project", str(self.root),
            "--session", "cli",
        ])
        self.assertEqual(status["sequence"], 0)
        denied = run_game_cli([
            "jeeves", "dragon-session-lesson", "--project", str(self.root),
            "--session", "cli", "--kind", "quest",
        ])
        self.assertFalse(denied["ok"])


if __name__ == "__main__":
    unittest.main()
