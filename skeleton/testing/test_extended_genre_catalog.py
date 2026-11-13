"""GameForge expanded genre registry and cross-surface contract tests."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

from skeleton.context.genre_catalog import GENRE_COUNT, GENRE_GROUPS, GENRE_ERA_VOTES, genre_catalog_payload
from skeleton.context.questionnaire import BRIEF_ERA_VOTES, intake, brief_ballots, normalise_brief
from skeleton.forge.eras import list_eras


LEGACY = {
    "action-adventure": "modern_aaa", "action": "modern_aaa", "adventure": "modern_aaa",
    "rpg": "crpg", "crpg": "crpg", "jrpg": "jrpg", "arpg": "soulslike",
    "soulslike": "soulslike", "strategy": "grand_strategy", "rts": "grand_strategy",
    "tactics": "tactics_grid", "platformer": "metroidvania", "metroidvania": "metroidvania",
    "simulation": "city_builder", "city-builder": "city_builder", "shooter": "boomer_shooter",
    "fps": "boomer_shooter", "horror": "horror_survival", "survival": "extraction_now",
    "extraction": "extraction_now", "roguelike": "roguelike", "roguelite": "roguelike",
    "stealth": "stealth", "immersive-sim": "immersive_sim", "fighting": "fighting_game",
    "puzzle": "indie_experimental", "deckbuilder": "deckbuilder", "card": "deckbuilder",
    "battle-royale": "battle_royale", "mmo": "mmorpg", "mmorpg": "mmorpg",
    "visual-novel": "visual_novel", "narrative": "walking_sim", "cozy": "cozy_wholesome",
    "arcade": "arcade_golden_age", "bullet-heaven": "bullet_heaven",
}


class ExtendedGenreContractTests(unittest.TestCase):
    def test_legacy_votes_are_unchanged(self):
        for name, era in LEGACY.items():
            self.assertEqual(GENRE_ERA_VOTES[name], era, name)
        self.assertEqual(len(LEGACY), 36)

    def test_all_158_tokens_have_valid_era_votes(self):
        self.assertEqual(GENRE_COUNT, 158)
        self.assertEqual(len(GENRE_ERA_VOTES), 158)
        self.assertEqual(len(GENRE_GROUPS), 11)
        self.assertEqual(GENRE_ERA_VOTES, BRIEF_ERA_VOTES["genre"])
        valid = set(list_eras())
        for token, era in GENRE_ERA_VOTES.items():
            self.assertRegex(token, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
            self.assertLessEqual(len(token), 48)
            self.assertIn(era, valid, token)
            self.assertEqual(normalise_brief({"genre": token})["genre"], token)

    def test_distinct_new_subgenres_vote_not_silent_default(self):
        examples = {
            "colony-sim": "city_builder",
            "tactical-rpg": "tactics_grid",
            "monster-tamer": "jrpg",
            "survival-horror": "horror_survival",
            "racing": "modern_aaa",
            "tower-defense": "tactics_grid",
            "rhythm": "arcade_golden_age",
            "card-battler": "deckbuilder",
        }
        for token, expected in examples.items():
            with self.subTest(token=token):
                self.assertEqual(intake({"genre": token}).era, expected)
                self.assertEqual(brief_ballots({"genre": token}), {expected: 2.0})

    def test_api_payload_is_bounded_and_deterministic(self):
        first, second = genre_catalog_payload(), genre_catalog_payload()
        self.assertEqual(first, second)
        self.assertEqual(first["count"], 158)
        self.assertEqual(first["version"], 1)
        self.assertEqual(len(first["groups"]), 11)
        self.assertEqual(
            {choice["id"]: choice["era"]
             for group in first["groups"] for choice in group["genres"]},
            GENRE_ERA_VOTES,
        )

    def test_frontend_catalog_matches_backend_exactly(self):
        source = (Path(__file__).resolve().parents[2]
                  / "frontend/src/skeletonForge/genreCatalog.ts").read_text(encoding="utf-8")
        groups = re.findall(r"genres: \[([\s\S]*?)\]", source)
        actual = [value for content in groups for value in re.findall(r"'([a-z0-9-]+)'", content)]
        expected = [token for group in GENRE_GROUPS for token, _ in group["genres"]]
        self.assertEqual(actual, expected)
        self.assertEqual(len(set(actual)), 158)

    def test_backend_http_route_advertises_same_catalog(self):
        from backend.routes.skeleton_gameforge import genres
        self.assertEqual(genres(), genre_catalog_payload())


if __name__ == "__main__":
    unittest.main()
