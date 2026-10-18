"""Jeeves, Dragon, and adversarial routes for every game-builder part."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.ai.game_builder.jeeves_app_runtime import (
    dispatch_app_action, JeevesAppCapabilityError,
)
from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, JeevesAppwideRuntime,
)
from skeleton.ai.game_builder.studio_role_triad import (
    PARTS, RoleTriadError, connect_system_triad, tool_triad,
)
from skeleton.ai.game_builder.studio_tool_fabric import BUILTIN_TOOLS


class RoleTriadTests(unittest.TestCase):
    def test_every_builtin_tool_has_three_role_routes(self):
        rows = tool_triad()
        self.assertEqual([row["tool_id"] for row in rows],
                         sorted(spec.tool_id for spec in BUILTIN_TOOLS))
        for row in rows:
            self.assertEqual(set(row) - {"tool_id"}, {"jeeves", "dragon", "adversarial"})
            self.assertTrue(all(row[role] for role in ("jeeves", "dragon", "adversarial")))

    def test_connection_exercises_every_part_and_rejects_tamper(self):
        receipt = connect_system_triad(seed=17, mirror_attempts=64, authorized=True)
        self.assertEqual([part["part"] for part in receipt["parts"]], list(PARTS))
        self.assertEqual(receipt["catalog_count"], len(BUILTIN_TOOLS))
        self.assertFalse(receipt["weights_changed"])
        self.assertFalse(receipt["reviewed_knowledge_promoted"])
        self.assertFalse(receipt["human_review_forged"])
        self.assertFalse(receipt["serving_transformers_updated"])
        self.assertFalse(receipt["perfect_builder_claimed"])
        by_name = {part["part"]: part for part in receipt["parts"]}
        for name in PARTS:
            lanes = by_name[name]["lanes"]
            self.assertEqual(set(lanes), {"jeeves", "dragon", "adversarial"})
            self.assertTrue(lanes["adversarial"]["evidence"]["rejected_tamper"])
            self.assertFalse(lanes["jeeves"]["weights_changed"])
            self.assertFalse(lanes["dragon"]["promotion"])
        knowledge = by_name["game_knowledge"]["lanes"]
        self.assertGreaterEqual(knowledge["jeeves"]["evidence"]["admitted_laws"], 20)
        self.assertTrue(knowledge["adversarial"]["evidence"]["holdout_absent_from_admitted"])
        self.assertFalse(knowledge["dragon"]["evidence"]["training_authorized"])
        upscale = by_name["asset_upscale"]["lanes"]["jeeves"]["evidence"]
        self.assertTrue(upscale["palette_preserved"])
        self.assertFalse(by_name["asset_style"]["lanes"]["jeeves"]["evidence"]["model_super_resolution"])
        play = by_name["gameplay"]["lanes"]["adversarial"]["evidence"]
        self.assertTrue(play["mirror_passed"])
        self.assertEqual(play["attempts"], 64)
        self.assertEqual(play["failed_count"], 0)
        self.assertFalse(play["human_ux_reviewed"])
        self.assertFalse(play["native_hardware_reviewed"])
        self.assertGreaterEqual(len(play["families"]), 12)
        timing = by_name["music_timing"]["lanes"]
        self.assertEqual(timing["jeeves"]["evidence"]["aligned_tempos"], 3)
        self.assertTrue(timing["dragon"]["evidence"]["frames_follow_bpm"])
        again = connect_system_triad(seed=17, mirror_attempts=64, authorized=True)
        self.assertEqual(again["digest"], receipt["digest"])

    def test_authorization_and_bounds_fail_closed(self):
        with self.assertRaises(PermissionError):
            connect_system_triad(seed=17, mirror_attempts=64, authorized=False)
        with self.assertRaises(RoleTriadError):
            connect_system_triad(seed=-1, mirror_attempts=64, authorized=True)
        with self.assertRaises(RoleTriadError):
            connect_system_triad(seed=17, mirror_attempts=8, authorized=True)

    def test_jeeves_and_appwide_dispatch_use_the_same_connection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "skeleton" / "ai" / "game_builder").mkdir(parents=True)
            (root / "skeleton" / "ai" / "game_builder" / "scene_editor.py").write_text(
                "def render():\n    return None\n", encoding="utf-8")
            inventory = AppwideInventory(root)
            inventory.scan()
            runtime = JeevesAppwideRuntime(inventory)
            with self.assertRaises(PermissionError):
                runtime.invoke("system.triad", {"seed": 17, "mirror_attempts": 64})
            with self.assertRaises(JeevesAppwideError):
                runtime.invoke("system.triad", {"seed": 17, "command": "rm"}, authorized=True)
            work = GameWorkspace.create(str(root / "work"), authorized=True)
            work.create_project("triad", "rpg", authorized=True)
            with self.assertRaises(PermissionError):
                dispatch_app_action(
                    work, "triad", "system.triad",
                    {"seed": 17, "mirror_attempts": 64}, authorized=False)
            with self.assertRaises(JeevesAppCapabilityError):
                dispatch_app_action(
                    work, "triad", "system.triad", {"seed": 17}, authorized=True)
            dispatched = dispatch_app_action(
                work, "triad", "system.triad",
                {"seed": 17, "mirror_attempts": 64}, authorized=True)
            direct = connect_system_triad(seed=17, mirror_attempts=64, authorized=True)
            self.assertEqual(dispatched["result"]["digest"], direct["digest"])
            self.assertFalse(dispatched["model_weights_changed"])
            self.assertFalse(dispatched["source_files_committed"])
            appwide = runtime.invoke(
                "system.triad", {"seed": 17, "mirror_attempts": 64}, authorized=True)
            self.assertEqual(appwide["result"]["digest"], direct["digest"])


if __name__ == "__main__":
    unittest.main()
