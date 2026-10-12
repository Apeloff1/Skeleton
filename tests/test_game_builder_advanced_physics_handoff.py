"""Game motion to independently simulated authored physics: replay gates and UI."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_handoff import (
    ORIGINS, PhysicsHandoffError, run_physics_handoff, verify_physics_handoff,
)
from skeleton.ai.game_builder.game_workspace_ui import render_workspace_html
from skeleton.ai.game_builder.game_workspace_server import _StudioHandler


class AdvancedCrossEnginePhysicsTests(unittest.TestCase):
    SOURCES={
        "platformer":("right","jump_right","wait"),
        "racing":("accelerate","accelerate","coast"),
        "flight":("throttle_up","climb","level"),
        "sailing":("hoist","trim_in","center_helm"),
    }

    def source(self,editor,seed=7,scene=None):
        return run_advanced_session(editor,actions=self.SOURCES[editor],
                                    seed=seed,scene=scene)

    def test_all_four_original_genres_produce_replayed_physical_games(self):
        self.assertEqual(ORIGINS,frozenset(self.SOURCES))
        for engine in self.SOURCES:
            with self.subTest(engine=engine):
                original=self.source(engine)
                untouched=deepcopy(original)
                bridge=run_physics_handoff(original)
                self.assertTrue(verify_physics_handoff(bridge))
                self.assertEqual(original,untouched)
                self.assertEqual(bridge["origin_editor"],engine)
                self.assertEqual(bridge["origin_session_digest"],original["digest"])
                self.assertEqual(bridge["origin_turns"],len(original["trace"]))
                self.assertEqual(bridge["physics_session"]["editor"],"physics")
                self.assertTrue(verify_advanced_session(
                    bridge["physics_session"],bridge["physics_settings"]))
                self.assertEqual(bridge["physics_scene"]["editor"],"physics")
                self.assertEqual(bridge["origin_scene_digest"],original["scene_digest"])
                self.assertEqual(bridge["policy"],
                                 "derived_training_exercise_not_live_genre_override")
                self.assertFalse(bridge["training_weights_promoted"])
                self.assertFalse(bridge["native_parity_verified"])
                self.assertEqual(bridge,run_physics_handoff(original))

    def test_original_authored_obstacles_become_genuine_physical_shapes(self):
        for engine in self.SOURCES:
            source=self.source(engine)
            bridge=run_physics_handoff(source)
            count=bridge["derived_obstacle_count"]
            self.assertGreater(count,0)
            self.assertLessEqual(count,4)
            fixtures=bridge["physics_scene"]["layout"]["fixtures"]
            self.assertEqual(len(fixtures),count)
            self.assertTrue(all(fixture["layer"]==3 for fixture in fixtures))
            self.assertTrue(all(fixture["half_size"]==[20,40,30]
                                for fixture in fixtures))
            self.assertTrue(verify_physics_handoff(bridge))

    def test_physics_bodies_reflect_each_verified_original_motion(self):
        profiles={}
        for engine in self.SOURCES:
            bridge=run_physics_handoff(self.source(engine))
            body=bridge["physics_scene"]["layout"]["bodies"][0]
            profiles[engine]=(body["mass"],body["material"])
            self.assertTrue(100<=body["position"][0]<=440)
            self.assertTrue(60<=body["position"][1]<=960)
            self.assertTrue(all(abs(v)<=bridge["physics_settings"]["speed_limit"]
                                for v in body["velocity"]))
            self.assertEqual(body["id"],"payload")
            self.assertNotEqual(body["position"],bridge["physics_scene"]["layout"]["goal"])
        self.assertEqual(profiles,{"platformer":(3,"wood"),
                                   "racing":(10,"metal"),
                                   "flight":(12,"metal"),
                                   "sailing":(9,"wood")})

    def test_upstream_action_progress_changes_downstream_training_input(self):
        original=run_advanced_session("platformer",actions=("right",),seed=2)
        changed=run_advanced_session("platformer",
                                     actions=("right","right","jump_right"),seed=2)
        first=run_physics_handoff(original)
        second=run_physics_handoff(changed)
        self.assertNotEqual(first["origin_session_digest"],
                            second["origin_session_digest"])
        self.assertNotEqual(first["origin_state_fingerprint"],
                            second["origin_state_fingerprint"])
        self.assertNotEqual(first["physics_scene"]["digest"],
                            second["physics_scene"]["digest"])
        self.assertTrue(verify_physics_handoff(first))
        self.assertTrue(verify_physics_handoff(second))

    def test_physically_executed_controls_change_signed_output(self):
        original=self.source("racing")
        idle=run_physics_handoff(original,physics_actions=("inspect",))
        moving=run_physics_handoff(original,physics_actions=("push:west","step:4"))
        self.assertNotEqual(idle["physics_session"]["digest"],
                            moving["physics_session"]["digest"])
        self.assertNotEqual(idle["physics_session"]["state"]["bodies"][0]["position"],
                            moving["physics_session"]["state"]["bodies"][0]["position"])
        self.assertTrue(verify_physics_handoff(moving))

    def test_authorized_setting_variants_affect_actual_physical_outcome(self):
        original=self.source("flight")
        fast=run_physics_handoff(original,
                 physics_options={"air_drag":0},
                 physics_actions=("inspect","step:4"))
        slow=run_physics_handoff(original,
                 physics_options={"air_drag":40},
                 physics_actions=("inspect","step:4"))
        self.assertNotEqual(
            fast["physics_session"]["state"]["bodies"][0]["velocity"],
            slow["physics_session"]["state"]["bodies"][0]["velocity"])
        self.assertTrue(verify_physics_handoff(fast))
        self.assertTrue(verify_physics_handoff(slow))

    def test_reject_unverified_or_impostor_origin_without_side_effects(self):
        for invalid in (
            {"editor":"physics"},
            {"editor":"flight","state":{"x":1000000}},
            "not a session",
        ):
            with self.assertRaises(PhysicsHandoffError):
                run_physics_handoff(invalid)
        origin=self.source("sailing")
        forgery=deepcopy(origin);forgery["state"]["fuel"]=1000000
        with self.assertRaises(PhysicsHandoffError):
            run_physics_handoff(forgery)
        changed=deepcopy(origin);changed["actions"][0]="create_cargo"
        with self.assertRaises(PhysicsHandoffError):
            run_physics_handoff(changed)

    def test_forbidden_override_and_unbounded_commands_denied(self):
        origin=self.source("flight")
        for overrides in (
            {"dimension":"3d"},
            {"goal_radius":200},
            {"max_bodies":8},
            {"initial_battery":100},
            {"collision_geometry":"aabb"},
        ):
            with self.assertRaises(PhysicsHandoffError):
                run_physics_handoff(origin,physics_options=overrides)
        with self.assertRaises(PhysicsHandoffError):
            run_physics_handoff(origin,physics_actions=["inspect"]*25)
        with self.assertRaises(PhysicsHandoffError):
            run_physics_handoff(origin,physics_actions=("teleport",))
        with self.assertRaises(PhysicsHandoffError):
            run_physics_handoff(origin,physics_options={"air_drag":False})

    def test_cross_engine_evidence_is_not_forgeable_into_weight_promotion(self):
        record=run_physics_handoff(self.source("racing"))
        changes=[
            ("training_weights_promoted",True),
            ("native_parity_verified",True),
            ("derived_obstacle_count",9000),
            ("origin_turns",42),
            ("physics_settings",{"gravity":0}),
            ("policy","live_engine_override"),
        ]
        for key,val in changes:
            with self.subTest(key=key):
                altered=deepcopy(record);altered[key]=val
                with self.assertRaises(PhysicsHandoffError):
                    verify_physics_handoff(altered)
        altered=deepcopy(record)
        altered["physics_session"]["state"]["finished"]=True
        with self.assertRaises(PhysicsHandoffError):
            verify_physics_handoff(altered)

    def test_original_source_with_signed_level_is_respected(self):
        editor="platformer"
        scene=make_advanced_scene(editor,seed=4,layout={
            "spawn_x":0,"exit_x":15,"hazards":[4,7],
            "collectibles":[6,11],"checkpoints":[8,12]})
        origin=run_advanced_session(editor,actions=("right","jump_right"),
                                    seed=4,scene=scene)
        record=run_physics_handoff(origin)
        self.assertEqual(record["origin_scene_digest"],scene["digest"])
        self.assertEqual(record["derived_obstacle_count"],2)
        self.assertEqual(
            record["physics_scene"]["layout"]["fixtures"][0]["position"][0],
            590+(4%7)*120)
        self.assertTrue(verify_physics_handoff(record))

    def test_local_studio_has_explicit_handoff_and_no_silent_promotion(self):
        html=render_workspace_html("A"*32).decode()
        self.assertIn('id="advanced-physics-handoff"',html)
        self.assertIn('"/api/physics-handoff"',html)
        self.assertIn('"platformer","racing","flight","sailing"',html)
        self.assertIn("training_weights_promoted:false",html)
        self.assertIn("origin_game_mutated",html)
        self.assertTrue(callable(_StudioHandler._post))

    def test_roundtrip_canonical_evidence_is_stable_and_bounded(self):
        evidence=run_physics_handoff(self.source("flight"),
                                      physics_actions=("inspect",))
        converted=json.loads(json.dumps(evidence,sort_keys=True))
        self.assertEqual(converted,evidence)
        self.assertTrue(verify_physics_handoff(converted))
        self.assertLess(len(json.dumps(evidence).encode()),110000)


if __name__=="__main__":
    unittest.main()
