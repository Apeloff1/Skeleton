"""Persistent authored NPC autonomy, relationship memory, time and LOD."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.npc_society_runtime import (
    SocietyError, make_society, choose_intent, society_tick,
    apply_world_event, society_replay, Memory, Mind,
)


class NPCSocietyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = forge_director(
            "society_world", seed=32267,
            regions=tuple(f"place_{n:02d}" for n in range(16)),
            quest_types=("main_story", "rival_story", "regional_story"),
            stages=3,
        )

    def test_hundreds_of_npcs_preserve_identity_with_adaptive_simulation(self):
        world = self.world
        society = make_society(world, 384, authorized=True)
        self.assertEqual(len(society.minds), 384)
        self.assertEqual(len({p.key for p in society.profiles}), 384)
        first = society.minds
        for _ in range(8):
            society = society_tick(
                society, world, player_scene="scene_00",
                active_budget=40, ambient_budget=64, authorized=True,
            )
        self.assertEqual(society.turn, 8)
        self.assertEqual(sum(m.lod=="active" for m in society.minds), 40)
        self.assertEqual(sum(m.lod=="ambient" for m in society.minds), 64)
        self.assertEqual(sum(m.lod=="dormant" for m in society.minds), 280)
        self.assertTrue(all(m.key==p.key for p,m in zip(society.profiles,society.minds)))
        self.assertTrue(any(m.energy != m0.energy for m,m0 in zip(society.minds,first)))
        self.assertTrue(any(m.skill > m0.skill for m,m0 in zip(society.minds,first)))
        self.assertEqual(society.digest, self.rebuild(384, 8).digest)

    def rebuild(self, number, steps):
        s=make_society(self.world, number, authorized=True)
        for _ in range(steps):
            s=society_tick(s,self.world,player_scene="scene_00",
                           active_budget=40,ambient_budget=64,authorized=True)
        return s

    def test_personal_motives_change_preferences_and_independent_actions(self):
        s=make_society(self.world, 12, authorized=True)
        citizen=s.profiles[0]
        before=s.minds[0]
        exhausted=replace(before, energy=0, stress=99)
        choice=choose_intent(citizen,exhausted,3)
        self.assertEqual(choice,"rest")
        stressed=replace(before, stress=0, energy=100, hunger=0,
                         belonging=100, supplies=10)
        alternative=choose_intent(citizen,stressed,1)
        self.assertIn(alternative,{"work","explore","protect","assist","socialize"})
        self.assertNotEqual(choice,alternative)
        self.assertGreater(len({p.profession for p in s.profiles}), 5)
        self.assertGreater(len({p.motive for p in s.profiles}), 4)

    def test_causal_event_perception_and_memory_change_bonds(self):
        s=make_society(self.world,18,authorized=True)
        player=s.minds[0].scene
        affected=[m.key for m in s.minds if m.scene==player]
        s2=apply_world_event(s,self.world,event="player_rescued_scholar",
                            subject="hero",scene=player,valence=90,
                            authorized=True)
        for before,after in zip(s.minds,s2.minds):
            if before.key in affected:
                self.assertEqual(after.belief_flags,("player_rescued_scholar",))
                self.assertIn("hero",dict(after.bonds))
                self.assertEqual(dict(after.bonds)["hero"],18)
                self.assertEqual(after.memories[-1].certainty,100)
            else:
                self.assertEqual(after,before)
        negative=apply_world_event(s2,self.world,event="player_stole_food",
                                   subject="hero",scene=player,valence=-100,
                                   authorized=True)
        self.assertLess(dict(negative.minds[0].bonds)["hero"],18)
        self.assertGreater(negative.minds[0].stress,s2.minds[0].stress)
        self.assertEqual(s2.digest,apply_world_event(
            s,self.world,event="player_rescued_scholar",
            subject="hero",scene=player,valence=90,authorized=True).digest)

    def test_no_private_crossworld_memory_or_nonphysical_travel(self):
        s=make_society(self.world,24,authorized=True)
        with self.assertRaises(PermissionError):
            society_tick(s,self.world,player_scene="scene_00",
                         active_budget=4,ambient_budget=4,authorized=False)
        with self.assertRaises(SocietyError):
            society_tick(s,self.world,player_scene="not_a_scene",
                         active_budget=4,ambient_budget=4,authorized=True)
        with self.assertRaises(SocietyError):
            apply_world_event(s,self.world,event="stranger_event",
                              subject="stranger",scene="scene_00",
                              valence=50,witnesses=("invented_actor",),
                              authorized=True)
        state=society_tick(s,self.world,player_scene="scene_00",
                           active_budget=24,ambient_budget=0,authorized=True)
        scene_links={a.key:set(a.links) for a in self.world.scenes}
        for old,new in zip(s.minds,state.minds):
            self.assertTrue(old.scene==new.scene or new.scene in scene_links[old.scene])

    def test_machine_evidence_and_replay_are_deterministic(self):
        a=society_replay(self.world,128,steps=12,player_scene="scene_02",
                         active_budget=24,ambient_budget=32,authorized=True)
        b=society_replay(self.world,128,steps=12,player_scene="scene_02",
                         active_budget=24,ambient_budget=32,authorized=True)
        self.assertEqual(a,b)
        self.assertEqual(a["full_population"],128)
        self.assertEqual(a["actively_simulated"],24)
        self.assertEqual(a["ambient"],32)
        self.assertEqual(a["persistent_dormant"],72)
        self.assertEqual(len(a["state_digests"]),12)
        self.assertEqual(a["final"]["turn"],12)

    def test_memory_capacity_is_bounded_and_is_not_infinitely_repeating(self):
        s=make_society(self.world,3,authorized=True)
        scene=s.minds[0].scene
        for i in range(45):
            s=apply_world_event(s,self.world,event=f"event_{i}",
                                subject="hero",scene=scene,valence=i%100,
                                authorized=True,witnesses=(s.minds[0].key,))
        self.assertEqual(len(s.minds[0].memories),24)
        self.assertTrue(all(m.origin=="observed" for m in s.minds[0].memories))
        self.assertLessEqual(len(s.minds[0].memories),24)


if __name__=="__main__":
    unittest.main()
