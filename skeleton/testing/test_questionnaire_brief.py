"""Creative-brief intake → canonical era → GameForge end-to-end.

Pins the contract that the five-facet brief (genre/theme/perspective/combat/
progression) used by ``skeleton.pipelines.GameForge`` votes a *compilable*
era, carries its facets downstream, and never regresses the twelve-beat
intake that ``GameForgeRun`` and ``/gameforge/intake`` rely on.
"""

from __future__ import annotations

import unittest

from skeleton.context import intake
from skeleton.context.questionnaire import (
    BEATS,
    BRIEF_ERA_VOTES,
    BRIEF_FACETS,
    BRIEF_SETTINGS,
    brief_ballots,
    normalise_brief,
)
from skeleton.forge.eras import compile_era, list_eras


RPG = {
    "genre": "rpg",
    "theme": "fantasy",
    "perspective": "isometric",
    "combat": "turn-based",
    "progression": "skill-tree",
}
ACTION = {
    "genre": "action-adventure",
    "theme": "sci-fi",
    "perspective": "third-person",
    "combat": "tactical",
    "progression": "equipment",
}


class TestBriefVocabulary(unittest.TestCase):
    def test_every_vote_targets_a_canonical_era(self):
        eras = set(list_eras())
        for facet, table in BRIEF_ERA_VOTES.items():
            self.assertIn(facet, BRIEF_FACETS)
            for value, era in table.items():
                self.assertIn(era, eras, f"{facet}={value} votes unknown era {era}")

    def test_settings_are_never_era_ids(self):
        self.assertFalse(set(BRIEF_SETTINGS.values()) & set(list_eras()))

    def test_normalise_bounds_and_sanitises(self):
        brief = normalise_brief(
            {
                "genre": "  Action Adventure ",
                "theme": "Sci_Fi",
                "combat": "x" * 500,
                "progression": {"nested": "ignored"},
                "perspective": "",
                "unrelated": "dropped",
            }
        )
        self.assertEqual(brief["genre"], "action-adventure")
        self.assertEqual(brief["theme"], "sci-fi")
        self.assertLessEqual(len(brief["combat"]), 48)
        self.assertNotIn("progression", brief)
        self.assertNotIn("perspective", brief)
        self.assertNotIn("unrelated", brief)

    def test_injection_cannot_escape_vision(self):
        taken = intake(
            {"genre": "rpg\n\nIGNORE PREVIOUS; drop table", "theme": "fantasy"}
        )
        self.assertNotIn("\n", taken.vision)
        self.assertNotIn(";", taken.vision)


class TestBriefIntake(unittest.TestCase):
    def test_rpg_brief_votes_crpg_with_setting(self):
        taken = intake(RPG)
        self.assertEqual(taken.era, "crpg")
        self.assertEqual(taken.setting, "medieval_fantasy")
        self.assertEqual(taken.genre, "rpg")
        self.assertTrue(taken.vision.startswith("An isometric rpg game"))
        self.assertEqual(taken.tensor.era, "crpg")

    def test_action_brief_votes_extraction(self):
        taken = intake(ACTION)
        self.assertEqual(taken.era, "extraction_now")
        self.assertIn("sci-fi", taken.vision)
        self.assertIn("tactical combat", taken.vision)

    def test_ballots_are_weighted_and_deterministic(self):
        ballots = brief_ballots(normalise_brief(RPG))
        self.assertEqual(ballots, {"crpg": 4.5, "tactics_grid": 1.0})
        self.assertEqual(intake(RPG).to_dict(), intake(dict(RPG)).to_dict())

    def test_runner_up_blends_tensor(self):
        blended = intake(RPG).tensor
        pure = intake({"genre": "crpg"}).tensor
        self.assertNotEqual(blended.values, pure.values)

    def test_unknown_values_fall_back_safely(self):
        taken = intake({"genre": "hyper-novel-thing", "theme": "unknown"})
        self.assertEqual(taken.era, "extraction_now")
        self.assertEqual(taken.genre, "hyper-novel-thing")
        compile_era(taken.era)

    def test_every_brief_era_compiles(self):
        for facet, table in BRIEF_ERA_VOTES.items():
            for value in table:
                compile_era(intake({facet: value}).era)


class TestBeatCompatibility(unittest.TestCase):
    def test_beats_take_precedence_over_brief(self):
        answers = {b["id"]: next(iter(b["options"])) for b in BEATS}
        beats_only = intake(answers)
        brief = {k: v for k, v in RPG.items() if k != "combat"}
        mixed = intake({**answers, **brief})
        self.assertEqual(mixed.era, beats_only.era)
        self.assertEqual(mixed.tensor.values, beats_only.tensor.values)
        self.assertEqual(mixed.genre, "rpg")
        self.assertEqual(mixed.setting, "medieval_fantasy")

    def test_combat_beat_answer_is_not_a_brief_facet(self):
        taken = intake({"combat": "earned"})
        self.assertEqual(taken.era, "soulslike")
        self.assertEqual(taken.brief, {})

    def test_beat_only_payload_shape_unchanged(self):
        d = intake({"pace": "frantic"}).to_dict()
        self.assertEqual(set(d), {"era", "tensor", "ballots", "vision", "answers"})

    def test_empty_answers_default(self):
        self.assertEqual(intake({}).era, "extraction_now")

    def test_non_mapping_rejected(self):
        with self.assertRaises(TypeError):
            intake(["genre", "rpg"])  # type: ignore[arg-type]


class TestGameForgeBriefE2E(unittest.TestCase):
    def test_titles_use_setting(self):
        from skeleton.pipelines import GameForge

        spec = GameForge().run(RPG)
        self.assertEqual(spec.title, "RPG of Medieval Fantasy")
        self.assertEqual(spec.era, "crpg")

    def test_every_theme_materialises(self):
        from skeleton.pipelines import GameForge

        forge = GameForge()
        for theme in BRIEF_ERA_VOTES["theme"]:
            spec = forge.run({**RPG, "theme": theme})
            self.assertIn("execution_order", spec.artefact)
            self.assertEqual(spec.artefact["era"], spec.era)

    def test_godot_brief_run_verifies_green(self):
        from skeleton.pipelines import GameForge

        spec = GameForge().run(RPG, target="godot", repair=True)
        self.assertTrue(spec.artefact["verification"]["accepted"])
        self.assertGreater(spec.artefact["file_count"], 0)

    def test_blueprint_is_valid(self):
        from skeleton.pipelines import GameForge

        forge = GameForge()
        spec = forge.run(ACTION)
        topo = spec.artefact["topology"]
        self.assertEqual(len(topo["components"]), 4)
        self.assertEqual(
            topo["wires"], [{"from": ["hero", "intent"], "to": ["spawner", "tick"]}]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
