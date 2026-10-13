"""Modular authored scenes, cinematic timestamps, NPC position and hardware budgets."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.npc_society_runtime import (
    make_society,society_tick,
)
from skeleton.ai.game_builder.modular_scene_compositor import (
    CompositionError,Transform,compose_scene,storyboard,
)


class ModularSceneDirectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "scene_modularity",seed=59271,
            regions=tuple(f"region_{i:02d}" for i in range(12)),
            quest_types=("main_story","escort_path","rival_story"),
            stages=3,
        )
        society=make_society(cls.world,96,authorized=True)
        cls.society=society_tick(
            society,cls.world,player_scene="scene_00",
            active_budget=40,ambient_budget=36,authorized=True)
        cls.scene=next(s for s in cls.world.scenes if s.cutscenes)
        cls.cutscene=cls.scene.cutscenes[0]

    def test_cinematic_timeline_produces_real_different_staged_frames(self):
        frames=storyboard(
            self.world,self.society,self.scene.key,self.cutscene.key,
            tier="desktop",authorized=True,
        )
        self.assertGreaterEqual(len(frames),5)
        self.assertEqual(frames[0].scene,self.scene.key)
        self.assertEqual(frames[0].world_digest,self.world.digest)
        self.assertEqual(frames[-1].cutscene,self.cutscene.key)
        self.assertGreater(len({f.digest for f in frames}),3)
        self.assertIn("soft amber sky",[f.lighting for f in frames])
        self.assertIn("wide original establishing shot",
                      [f.camera for f in frames])
        self.assertTrue(any(f.subtitle for f in frames))
        self.assertIn("actor_emote:hero",frames[-1].active_cues)
        self.assertEqual(frames,
                         storyboard(self.world,self.society,self.scene.key,
                                    self.cutscene.key,tier="desktop",
                                    authorized=True))

    def test_scene_cast_and_npcs_are_actual_no_teleportations(self):
        frame=compose_scene(self.world,self.society,self.scene.key,
                            tier="handheld",authorized=True)
        citizen_keys={p.key for p,m in zip(self.society.profiles,self.society.minds)
                      if m.scene==self.scene.key and m.lod!="dormant"}
        rendered={a.key for a in frame.actors if
                  a.entity_source=="observed_npc_society"}
        self.assertTrue(rendered<=citizen_keys)
        self.assertLessEqual(len(frame.actors),max(18,len(self.scene.cast)))
        self.assertEqual(frame.visible_npcs,len(rendered))
        self.assertEqual(frame.dormant_npcs_outside_view,
                         len(self.society.minds)-len(rendered))
        self.assertFalse(frame.payload()["renderer_2d_or_3d_verified"])

    def test_hero_cinematic_actor_expression_changes_coherently(self):
        at0=compose_scene(self.world,self.society,self.scene.key,
                          cutscene_key=self.cutscene.key,
                          at_ms=0,authorized=True)
        at2000=compose_scene(self.world,self.society,self.scene.key,
                             cutscene_key=self.cutscene.key,
                             at_ms=2000,authorized=True)
        hero0=next(a for a in at0.actors if a.key=="hero")
        hero2=next(a for a in at2000.actors if a.key=="hero")
        self.assertEqual(hero0.expression,"neutral")
        self.assertEqual(hero2.expression,"react to outcome")
        self.assertNotEqual(at0.digest,at2000.digest)

    def test_foreign_npcs_unsanctioned_timeline_and_invalid_transform_rejected(self):
        foreign=forge_director(
            "another_story_world",seed=59272,
            regions=tuple(f"region_{i:02d}" for i in range(12)),
            quest_types=("main_story","escort_path"),
            stages=2,
        )
        with self.assertRaises(CompositionError):
            compose_scene(foreign,self.society,self.scene.key,authorized=True)
        with self.assertRaises(CompositionError):
            compose_scene(self.world,self.society,self.scene.key,
                          cutscene_key="other_cinema",authorized=True)
        with self.assertRaises(CompositionError):
            compose_scene(self.world,self.society,self.scene.key,
                          tier="imaginary_console",authorized=True)
        with self.assertRaises(PermissionError):
            compose_scene(self.world,self.society,self.scene.key,
                          authorized=False)
        with self.assertRaises(CompositionError):
            Transform(0,0,0,0,0)


if __name__=="__main__":
    unittest.main()
