"""Tests for the GameForge end-to-end orchestrator."""

from __future__ import annotations

import unittest


class TestGameForgeIntake(unittest.TestCase):
    def test_intake_returns_structured_result(self):
        from skeleton.pipelines import GameForge

        forge = GameForge()
        result = forge.intake({
            "genre": "rpg",
            "theme": "fantasy",
            "perspective": "isometric",
            "combat": "turn-based",
            "progression": "skill-tree",
        })
        self.assertEqual(result["era"], "medieval_fantasy")
        self.assertIn("isometric", result["vision"])


class TestGameForgeRun(unittest.TestCase):
    ANSWERS = {
        "genre": "action-adventure",
        "theme": "sci-fi",
        "perspective": "third-person",
        "combat": "tactical",
        "progression": "equipment",
    }

    def test_run_produces_game_spec(self):
        from skeleton.pipelines import GameForge

        forge = GameForge()
        spec = forge.run(self.ANSWERS, title="Nebula Raiders")

        self.assertEqual(spec.title, "Nebula Raiders")
        self.assertEqual(spec.era, "extraction_now")
        self.assertTrue(spec.blueprint_id.startswith("bp-"))
        self.assertEqual(len(spec.npcs), 2)
        self.assertIsNotNone(spec.game_logic)
        self.assertIsNotNone(spec.animation)

    def test_run_with_genesis_uses_wired_forge(self):
        from skeleton.genesis import Genesis
        from skeleton.pipelines import GameForge

        genesis = Genesis(seed=42).boot()
        forge = GameForge(genesis=genesis)
        spec = forge.run(self.ANSWERS)
        self.assertIn("execution_order", spec.artefact)
        self.assertEqual(len(spec.artefact["execution_order"]), 4)

    def test_run_derives_title_when_missing(self):
        from skeleton.pipelines import GameForge

        forge = GameForge()
        spec = forge.run(self.ANSWERS)
        self.assertTrue(len(spec.title) > 0)
        self.assertIn("Action-Adventure", spec.title)

    def test_events_published(self):
        from skeleton.genesis import Genesis
        from skeleton.pipelines import GameForge

        genesis = Genesis(seed=42).boot()
        received = []
        genesis.bus.subscribe("gameforge.run.completed", lambda e: received.append(e.payload))

        forge = GameForge(genesis=genesis)
        forge.run(self.ANSWERS)
        self.assertEqual(len(received), 1)
        self.assertIn("spec_id", received[0])

    def test_spec_serialization(self):
        from skeleton.pipelines import GameForge

        forge = GameForge()
        spec = forge.run(self.ANSWERS)
        d = spec.to_dict()
        for key in ("spec_id", "title", "vision", "era", "blueprint_id", "npcs", "game_logic", "animation"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
