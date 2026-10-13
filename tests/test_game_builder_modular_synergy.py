"""Executable NPC + director + mission composition on actual authored quests."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.quest_director_solver import solve_quest
from skeleton.ai.game_builder.quest_scene_engine import DirectorAction
from skeleton.ai.game_builder.modular_mission_runtime import (
    MissionError, Formula, MissionFact, atom, mission_initial,
    replay_mission_book,
)
from skeleton.ai.game_builder.modular_mission_compiler import compile_modular_missions
from skeleton.ai.game_builder.modular_director_session import (
    IntegrationError, orchestrator_plan, open_director_session,
    director_session_step, simulate_director,
)
from skeleton.ai.game_builder.director_capability_graph import (
    CapabilityError, resolve_capabilities, TIERS,
)


class CompleteEngineSynergyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "coherent_mission_society",seed=32629,
            regions=tuple(f"district_{i:02d}" for i in range(12)),
            quest_types=("main_story","escort_leash","rival_story",
                         "regional_story","crafting","investigation"),
            stages=3,main_goal="Preserve the river communities without destroying their autonomy.",
        )
        cls.creative=solve_quest(cls.world,"quest_00",
                                 strategy="creative",authorized=True)
        cls.optional=solve_quest(cls.world,"quest_00",
                                 strategy="creative",optional=True,authorized=True)

    def test_real_canonical_replay_creates_independently_proven_mission_progress(self):
        book=compile_modular_missions(self.world,authorized=True)
        self.assertEqual(book.invariant_goal,self.world.bible.invariant_goal)
        main=book.missions[0]
        self.assertEqual(main.lane,"main")
        self.assertEqual(len(main.stages),3)
        self.assertEqual(main.stages[0].victory.op,"any")
        self.assertEqual(len(main.stages[0].victory.children),3)
        state=replay_mission_book(book,self.world,self.creative.replay,
                                  authorized=True)
        self.assertEqual(dict(state.stage_indexes)["quest_00"],3)
        self.assertIn("quest_00",state.completed)
        self.assertEqual(len([x for x in state.outcomes if x.mission=="quest_00"]),3)
        self.assertEqual(len(state.facts),len(self.creative.replay.actions))
        enriched=replay_mission_book(book,self.world,self.optional.replay,
                                     authorized=True)
        self.assertEqual(len(enriched.outcomes),3)
        self.assertEqual(sum(x.optional_completed for x in enriched.outcomes),3)
        self.assertGreater(sum(x.reward for x in enriched.outcomes),
                           sum(x.reward for x in state.outcomes))

    def test_advanced_boolean_and_threshold_victory_not_rigid_single_answer(self):
        facts=(
            MissionFact("fight","guard","scene_01",1,1,"proof_1"),
            MissionFact("negotiate","guard","scene_01",2,1,"proof_2"),
            MissionFact("escort_follow","friend","scene_02",3,1,"proof_3"),
        )
        options=Formula("any",children=(
            Formula("all",children=(atom("fight","guard"),atom("escort_follow","friend"))),
            Formula("all",children=(atom("negotiate","guard"),atom("escort_follow","friend"))),
        ))
        self.assertTrue(options.evaluate(facts))
        self.assertFalse(options.evaluate(facts[:2]))
        alternative=Formula("at_least",children=(
            atom("fight","guard"),atom("negotiate","guard"),
            atom("escort_follow","friend")),threshold=2)
        self.assertTrue(alternative.evaluate(facts[:2]))
        self.assertFalse(Formula("at_least",children=alternative.children,
                                 threshold=3).evaluate(facts[:2]))
        with self.assertRaises(MissionError):
            Formula("at_least",children=alternative.children,threshold=4)

    def test_real_authoring_actions_drive_96_npc_memories_and_quest_changes(self):
        simulation=simulate_director(
            self.world,self.creative.replay.actions,population=96,
            tier="desktop",authorized=True,
        )
        report=simulation.performance
        self.assertEqual(simulation.session.story,self.creative.replay.final)
        self.assertEqual(simulation.session.society.turn,
                         self.creative.replay.final.turn)
        self.assertEqual(report["population"],96)
        self.assertEqual(report["npc_active"],64)
        self.assertEqual(report["npc_ambient"],32)
        self.assertEqual(report["quest_stages_completed"],3)
        self.assertGreater(report["observed_memory_count"],0)
        self.assertGreater(report["relationship_count"],0)
        self.assertEqual(len(simulation.checkpoints),
                         len(self.creative.replay.actions))
        self.assertEqual(simulation.digest,simulate_director(
            self.world,self.creative.replay.actions,population=96,
            tier="desktop",authorized=True).digest)

    def test_scarce_device_tier_maintains_population_and_lowers_active_detail(self):
        simulation=simulate_director(
            self.world,self.creative.replay.actions,population=256,
            tier="mobile",authorized=True)
        report=simulation.performance
        self.assertEqual(report["population"],256)
        self.assertEqual(report["npc_active"],28)
        self.assertEqual(report["npc_ambient"],64)
        self.assertEqual(report["npc_persistent_dormant"],164)
        self.assertEqual(report["quest_stages_completed"],3)
        self.assertEqual(simulation.session.society.turn,
                         simulation.session.story.turn)

    def test_no_foreign_world_or_unsupported_provider_claims(self):
        with self.assertRaises(PermissionError):
            simulate_director(self.world,self.creative.replay.actions,
                              population=96,authorized=False)
        with self.assertRaises(CapabilityError):
            resolve_capabilities(("npc.language_model",),
                                  tier=TIERS["desktop"])
        with self.assertRaises(CapabilityError):
            resolve_capabilities(("product.platform_store",),
                                  tier=TIERS["high_end"])
        plan=orchestrator_plan("desktop")
        self.assertIn("director.synergy",[x.key for x in plan.selected])
        self.assertFalse(any(x.privileges for x in plan.selected))
        with self.assertRaises(IntegrationError):
            simulate_director(
                self.world,(*self.creative.replay.actions,
                            DirectorAction("travel","invented",
                                           self.creative.replay.final.scene)),
                population=96,authorized=True,
            )
        with self.assertRaises(PermissionError):
            open_director_session(self.world,population=96,authorized=False)

    def test_event_evidence_has_valid_source_links_and_logical_story_clock(self):
        simulation=simulate_director(
            self.world,self.creative.replay.actions,population=32,
            tier="handheld",authorized=True)
        facts=simulation.session.missions.facts
        self.assertEqual(len(facts),len(self.creative.replay.actions))
        self.assertEqual(tuple(sorted(f.turn for f in facts)),
                         tuple(f.turn for f in facts))
        self.assertTrue(all(len(f.source_digest)==64 for f in facts))
        self.assertEqual(simulation.performance["world_turns"],
                         simulation.session.society.turn)


if __name__=="__main__":
    unittest.main()
