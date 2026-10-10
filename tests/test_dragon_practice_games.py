"""Original Dragon practice game packs: real solvable worlds and offline export."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.contracts import canonical_json
from skeleton.ai.game_builder.playable_export import (
    PlayableExportError, write_playable_html,
)
from skeleton.ai.game_builder.playable_simulation import verify_replay
from skeleton.ai.game_builder.practice_game_library import (
    PACK_ROOT, OriginalPracticeGame, PracticeGameError,
    list_practice_games, load_practice_game, render_practice_game,
)


class DragonPracticeGameTests(unittest.TestCase):
    def test_one_hundred_packs_are_distinct_solved_original_games(self):
        names = list_practice_games(authorized=True)
        self.assertEqual(len(names), 100)
        self.assertEqual(names[0], "dragon-practice-001")
        self.assertEqual(names[-1], "dragon-practice-100")
        unique_worlds = set()
        layouts = set()
        total_moves = 0
        hazard_count = 0
        for name in names:
            with self.subTest(name=name):
                game = load_practice_game(name, authorized=True)
                self.assertIsInstance(game, OriginalPracticeGame)
                self.assertEqual(game.game_id, name)
                self.assertNotIn(game.world.digest, unique_worlds)
                unique_worlds.add(game.world.digest)
                layout = game.world.levels[0].rows
                self.assertNotIn(layout, layouts)
                layouts.add(layout)
                self.assertEqual(game.proof.final_state.status, "won")
                self.assertEqual(
                    game.proof.final_state.health,
                    game.world.intent.starting_health,
                )
                verify_replay(game.world, game.proof, authorized=True)
                self.assertGreater(len(game.proof.action_receipts), 0)
                self.assertFalse(game.receipt()["release_authorized"])
                self.assertFalse(game.receipt()["memory_promotion_authorized"])
                total_moves += len(game.proof.action_receipts)
                hazard_count += len(game.world.levels[0].hazards)
        self.assertGreater(total_moves, 1000)
        self.assertGreater(hazard_count, 100)

    def test_original_game_exports_as_reproducible_offline_csp_html(self):
        for name in ("dragon-practice-001", "dragon-practice-050",
                     "dragon-practice-100"):
            with self.subTest(game=name):
                game = load_practice_game(name, authorized=True)
                bundle = render_practice_game(name, authorized=True)
                self.assertEqual(bundle.world_digest, game.world.digest)
                self.assertIn("Content-Security-Policy", bundle.html)
                self.assertIn(game.world.intent.title, bundle.html)
                self.assertNotIn("https://", bundle.html)
                self.assertLess(len(bundle.html), 1_000_000)

    def test_practice_game_inventory_and_load_require_boolean_authority(self):
        for invalid in (1, "true", None, 0):
            with self.subTest(invalid=invalid):
                with self.assertRaises(PermissionError):
                    list_practice_games(authorized=invalid)
                with self.assertRaises(PermissionError):
                    load_practice_game("dragon-practice-001", authorized=invalid)
        for invalid in ("../../secret", "dragon-practice-000/..", "", None, 42):
            with self.subTest(invalid=invalid):
                with self.assertRaises(PracticeGameError):
                    load_practice_game(invalid, authorized=True)
        with self.assertRaises(PracticeGameError):
            load_practice_game("dragon-practice-999", authorized=True)

    def test_tampered_game_map_or_rights_state_is_never_loaded(self):
        first = PACK_ROOT / "dragon-practice-001.json"
        body = json.loads(first.read_text(encoding="utf-8"))
        with TemporaryDirectory() as temp:
            location = Path(temp)
            sample = location / first.name
            for mutation in ("wall", "solvability", "rights", "duplicate"):
                candidate = json.loads(canonical_json(body))
                if mutation == "wall":
                    candidate["rows"][0] = "." + candidate["rows"][0][1:]
                elif mutation == "solvability":
                    candidate["safe_solution"] = ["down"]
                elif mutation == "rights":
                    candidate["release_state"] = "hardware_verified"
                serialized = canonical_json(candidate) + "\n"
                if mutation == "duplicate":
                    serialized = serialized.replace(
                        '"schema":', '"schema":"forged","schema":', 1,
                    )
                sample.write_text(serialized, encoding="utf-8")
                with patch(
                    "skeleton.ai.game_builder.practice_game_library.PACK_ROOT",
                    location,
                ):
                    with self.subTest(mutation=mutation):
                        with self.assertRaises(PracticeGameError):
                            load_practice_game("dragon-practice-001", authorized=True)

    def test_atomic_export_does_not_overwrite_existing_operator_file(self):
        bundle = render_practice_game("dragon-practice-001", authorized=True)
        with TemporaryDirectory() as temp:
            target = Path(temp) / "game.html"
            target.write_text("operator-owned original", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_playable_html(
                    bundle, target, authorized=True, overwrite=False,
                )
            self.assertEqual(
                target.read_text(encoding="utf-8"), "operator-owned original",
            )
            target.unlink()
            write_playable_html(bundle, target, authorized=True, overwrite=False)
            self.assertEqual(target.read_text(encoding="utf-8"), bundle.html)
            with self.assertRaises(FileExistsError):
                write_playable_html(
                    bundle, target, authorized=True, overwrite=False,
                )


if __name__ == "__main__":
    unittest.main()
