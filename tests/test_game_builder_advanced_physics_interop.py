"""Original cross-engine physics rehearsals, scene provenance and collision custody."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_physics_interop import (
    SCHEMA,SUPPORTED,PHYSICAL_ACTIONS,PhysicsInteropError,
    rehearse_physics_encounter,verify_physics_encounter,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session,verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.system_editors import make_editor_document


class CrossFamilyPhysicsRehearsalTests(unittest.TestCase):
    def source(self,editor,settings=None,actions=(),*,seed=0,change=None):
        doc=make_editor_document(editor,settings)
        source=make_advanced_scene(editor,settings,seed=seed)
        if change:
            layout=deepcopy(source["layout"])
            change(layout)
            source=make_advanced_scene(editor,settings,seed=seed,layout=layout)
        gameplay=run_advanced_session(editor,settings,actions,
                                      seed=seed,scene=source)
        self.assertTrue(verify_advanced_session(gameplay,settings))
        return gameplay

    def test_all_three_families_replay_actual_original_source(self):
        self.assertEqual(set(SUPPORTED),{"platformer","racing","sandbox"})
        for editor in SUPPORTED:
            with self.subTest(editor=editor):
                source=self.source(editor,seed=3)
                before=deepcopy(source)
                proof=rehearse_physics_encounter(source)
                self.assertEqual(proof["schema"],SCHEMA)
                self.assertEqual(source,before)
                self.assertEqual(proof["source_scene_digest"],
                                 source["scene"]["digest"])
                self.assertEqual(proof["source_session_digest"],source["digest"])
                self.assertEqual(proof["physics_scene"]["editor"],"physics")
                self.assertEqual(proof["physics_session"]["editor"],"physics")
                self.assertTrue(verify_physics_encounter(proof,source))
                self.assertFalse(proof["source_gameplay_mutated"])
                self.assertFalse(proof["automatic_promotion_allowed"])
                self.assertFalse(proof["native_hardware_verified"])

    def test_physical_platformer_replay_detects_actual_signed_spikes(self):
        session=self.source("platformer",seed=1)
        proof=rehearse_physics_encounter(
            session,actions=("push:east",)*8)
        fixtures=proof["physics_scene"]["layout"]["fixtures"]
        source_hazards=session["scene"]["layout"]["hazards"]
        self.assertEqual(len(fixtures),min(8,len(source_hazards)))
        self.assertEqual([x["source_id"] for x in proof["witnesses"]],
                         source_hazards[:8])
        self.assertEqual(proof["physics_scene"]["layout"]["bodies"][0]["mask"],1)
        self.assertGreater(proof["observed_fixture_impacts"],0)
        self.assertTrue(proof["observed_impact"])
        self.assertTrue(verify_physics_encounter(proof,session))

    def test_racing_player_can_physically_avoid_obstacle_by_real_lane(self):
        settings={"track_length":80,"laps":2}
        center=self.source("racing",settings,seed=0)
        avoided=self.source("racing",settings,("steer_right",),seed=0)
        center_proof=rehearse_physics_encounter(center,settings)
        avoiding_proof=rehearse_physics_encounter(avoided,settings)
        self.assertEqual(center_proof["witnesses"][0]["source_type"],
                         "original_track_obstacle")
        self.assertEqual(center_proof["witnesses"][0]["layer"],3)
        self.assertEqual(avoiding_proof["witnesses"][0]["layer"],2)
        self.assertTrue(center_proof["observed_impact"])
        self.assertFalse(avoiding_proof["observed_impact"])
        self.assertTrue(verify_physics_encounter(center_proof,center,settings))
        self.assertTrue(verify_physics_encounter(avoiding_proof,avoided,settings))

    def test_authored_world_rehearsal_uses_real_terrain_and_road_passability(self):
        source=self.source("sandbox",seed=2)
        proof=rehearse_physics_encounter(source)
        self.assertTrue(proof["witnesses"])
        self.assertLessEqual(len(proof["witnesses"]),8)
        ids={tile["id"] for tile in source["scene"]["layout"]["tiles"]
             if tile["building"] is not None or tile["terrain"]=="ridge"}
        self.assertTrue(all(w["source_id"] in ids for w in proof["witnesses"]))
        self.assertTrue(verify_physics_encounter(proof,source))

    def test_signed_source_modification_rejects_unearned_physical_outcomes(self):
        session=self.source("platformer",seed=5)
        proof=rehearse_physics_encounter(session)
        for change in (
            lambda p:p.update(observed_impact=not p["observed_impact"]),
            lambda p:p.update(source_scene_digest="0"*64),
            lambda p:p["witnesses"][0].update(layer=2),
            lambda p:p["physics_session"]["state"].update(contacts=999),
            lambda p:p["physics_scene"]["layout"]["fixtures"].clear(),
        ):
            forged=deepcopy(proof)
            change(forged)
            with self.assertRaises(PhysicsInteropError):
                verify_physics_encounter(forged,session)

    def test_replay_is_not_approved_from_mutated_source_session(self):
        source=self.source("platformer",seed=0)
        good=rehearse_physics_encounter(source)
        modified=deepcopy(source)
        modified["state"]["health"]=9999
        with self.assertRaises(PhysicsInteropError):
            verify_physics_encounter(good,modified)
        modified=deepcopy(source)
        modified["scene"]["layout"]["hazards"]=[]
        with self.assertRaises(PhysicsInteropError):
            verify_physics_encounter(good,modified)

    def test_policy_gates_illegal_actions_and_unreviewed_origins(self):
        source=self.source("platformer")
        for actions in ((),("teleport",),("fan:on",),["push:east"]*33,
                        ("push:east",13),("attach:0",)):
            with self.subTest(actions=actions):
                with self.assertRaises(PhysicsInteropError):
                    rehearse_physics_encounter(source,actions=actions)
        unrelated=self.source("puzzle")
        with self.assertRaises(PhysicsInteropError):
            rehearse_physics_encounter(unrelated)

    def test_source_configuration_and_scene_are_required(self):
        source=self.source("racing",{"laps":1},seed=2)
        with self.assertRaises(PhysicsInteropError):
            rehearse_physics_encounter(source,{"laps":3})
        no_scene=run_advanced_session("racing",{"laps":1},seed=2)
        with self.assertRaises(PhysicsInteropError):
            rehearse_physics_encounter(no_scene,{"laps":1})
        self.assertFalse(rehearse_physics_encounter(source,{"laps":1})
                         ["native_hardware_verified"])

    def test_no_source_fabrication_when_original_game_is_win_or_failure(self):
        # Finite physics rehearsal never mints completion of the parent game.
        original=self.source("platformer",seed=0)
        winning=False
        report=rehearse_physics_encounter(original)
        self.assertEqual(original["state"]["finished"],winning)
        self.assertEqual(report["physics_session"]["state"]["geometry_mode"],"aabb")
        self.assertFalse(report["physics_session"]["terminal"])
        self.assertNotIn("source_mutated",report)
        self.assertTrue(verify_physics_encounter(report,original))

    def test_supported_physical_command_set_remains_finite(self):
        self.assertLessEqual(len(PHYSICAL_ACTIONS),12)
        self.assertNotIn("select:7",PHYSICAL_ACTIONS)
        self.assertNotIn("magnet:on",PHYSICAL_ACTIONS)


if __name__=="__main__":
    unittest.main()
