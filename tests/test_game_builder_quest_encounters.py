"""Spatial, noncolliding escort and timed-combat quest mechanics really execute."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_encounter_runtime import (
    EncounterError, EncounterSpec, encounter_initial, encounter_options,
    encounter_advance, encounter_play, encounter_verify, demonstrate_encounter,
)


class SpatialQuestTests(unittest.TestCase):
    ROUTE = ((1,1),(2,1),(3,1),(4,1),(4,2),(4,3),(5,3),(6,3))

    def make(self, kind, **kwargs):
        return EncounterSpec(
            key="original_spatial_quest", kind=kind,
            path=self.ROUTE, **kwargs,
        )

    def test_original_follow_and_noncolliding_leash_escort_proofs(self):
        for kind in ("escort_path", "escort_leash", "escort_introduction"):
            with self.subTest(kind=kind):
                game = self.make(kind)
                proof = demonstrate_encounter(game, authorized=True)
                self.assertEqual(proof.final.status, "won")
                self.assertEqual(proof.final.player, self.ROUTE[-1])
                self.assertEqual(proof.final.escort, self.ROUTE[-1])
                self.assertEqual(proof.final.escort_index, len(self.ROUTE)-1)
                self.assertLess(proof.final.turn, game.deadline)
                self.assertEqual(proof.final.player, proof.final.escort)
                # Identical tiles are *allowed*: companion has no collider.
                self.assertEqual(proof.digest, demonstrate_encounter(
                    game, authorized=True).digest)
                encounter_verify(game, proof)
                if kind == "escort_introduction":
                    self.assertTrue(proof.final.greeted)
                    self.assertEqual(proof.actions[-1], "introduce")
                else:
                    self.assertFalse(proof.final.greeted)

    def test_escort_cannot_teleport_or_enter_invalid_region(self):
        game = self.make("escort_leash")
        state = encounter_initial(game)
        with self.assertRaises(EncounterError):
            encounter_advance(game, state, "teleport", authorized=True)
        with self.assertRaises(PermissionError):
            encounter_advance(game, state, "east", authorized=False)
        with self.assertRaises(EncounterError):
            EncounterSpec(key="teleport_test", kind="escort_path",
                          path=((0,0),(5,5)))
        self.assertIn("east", encounter_options(game, state))
        one = encounter_advance(game, state, "east", authorized=True)
        self.assertEqual(one.player, one.escort)
        self.assertEqual(one.turn, 1)

    def test_time_bound_rival_and_waves_resolve_from_real_combat(self):
        for kind in ("combat", "rival_combat", "timed_combat",
                     "timed_rival_combat", "survival_waves", "reinforcement"):
            game = self.make(kind, waves=5, deadline=40)
            proof = demonstrate_encounter(game, authorized=True)
            self.assertEqual(proof.final.status, "won")
            self.assertEqual(proof.final.waves_cleared, 5)
            self.assertGreater(proof.final.health, 0)
            self.assertGreater(proof.final.turn, 5)
            self.assertEqual(proof.final.method, "direct_combat")
            encounter_verify(game, proof)

    def test_multiple_valid_combat_methods_and_optional_reinforcements(self):
        game = self.make("timed_rival_combat", waves=1, deadline=12)
        direct = encounter_play(game, ("attack",), authorized=True)
        peaceful = encounter_play(game, ("negotiate",), authorized=True)
        reinforced = encounter_play(game, ("reinforce","attack"),
                                    authorized=True)
        for proof in (direct, peaceful, reinforced):
            self.assertEqual(proof.final.status, "won")
            encounter_verify(game, proof)
        self.assertEqual(direct.final.method, "direct_combat")
        self.assertEqual(peaceful.final.method, "negotiation")
        self.assertGreater(reinforced.final.health, direct.final.health)
        self.assertNotEqual(peaceful.digest, direct.digest)

    def test_timed_escort_failure_and_health_evidence_cannot_be_forged(self):
        game = self.make("escort_path", deadline=8)
        lost = encounter_play(game, ("wait",)*8, authorized=True)
        self.assertEqual(lost.final.status, "lost")
        with self.assertRaises(EncounterError):
            encounter_advance(game, lost.final, "east", authorized=True)
        battle = self.make("rival_combat", waves=4, deadline=9, health=2)
        fail = encounter_play(battle, ("wait",), authorized=True)
        self.assertEqual(fail.final.status, "lost")
        good = demonstrate_encounter(self.make("combat"), authorized=True)
        with self.assertRaises(EncounterError):
            encounter_verify(self.make("rival_combat"), good)
        bad = replace(good, final=replace(good.final, health=99))
        with self.assertRaises(EncounterError):
            encounter_verify(self.make("combat"), bad)

    def test_resource_budgets_and_identity(self):
        with self.assertRaises(EncounterError):
            self.make("escort_leash", leash=0)
        with self.assertRaises(EncounterError):
            self.make("escort_path", waves=13)
        with self.assertRaises(EncounterError):
            self.make("timed_combat", deadline=3)
        with self.assertRaises(PermissionError):
            demonstrate_encounter(self.make("combat"), authorized=False)


if __name__ == "__main__":
    unittest.main()
