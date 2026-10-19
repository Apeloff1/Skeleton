"""Adversarial verification of controlled vs real Godot wind-dash playthrough."""
from copy import deepcopy
import unittest

from skeleton.jeeves.game_frontier_native_dash_audit import (
    verify_native_wind_dash_playthrough,
)
from skeleton.jeeves.game_frontier_native_quest_session import NativeQuestSessionError


def fixture():
    dispatch={
        "schema":"skeleton.game.native_godot_dispatch.v1",
        "actor_id":"hero","scene_candidate_digest":"c"*64,
        "signed_gdd_digest":"d"*64,"receipt_digest":"b"*64,
        "expected_local_level":2,
        "expected_unlocked_skills":{"wind_dash":2},
    }
    capture=[]
    for i in range(5):
        capture.append({
            "schema":"skeleton.game.native_physics_observation.v1",
            "native_engine":"godot4_physics",
            "authority":"untrusted_native_candidate_observation_not_attested",
            "scene_candidate_digest":"c"*64,"signed_gdd_digest":"d"*64,
            "native_tick":i,"fps":60,
            "actors":[{
                "id":"hero","world_xyz_m":[0.,0.,0.],
                "velocity_xyz_mps":[0.,0.,0.],
                "physics_body":{"mode":"rigid","mass_kg":2.},
            }],
        })
    dash=deepcopy(capture)
    for i in (2,3,4):
        dash[i]["actors"][0]["velocity_xyz_mps"]=[3.,0.,0.]
    receipt={
        "schema":"skeleton.game.approved_local_wind_dash_activation.v1",
        "actor_id":"hero","scene_candidate_digest":"c"*64,
        "signed_gdd_digest":"d"*64,"approved_dispatch_digest":"b"*64,
        "skill":"wind_dash","skill_required_level":2,"current_level":2,
        "source_game_tick":2,"bounded_impulse_ns":6.,
        "player_mass_kg":2.,"impulse_world_xyz_ns":[6.,0.,0.],
        "velocity_before_world_xyz_mps":[0.,0.,0.],
        "input_mode":"explicit_native_ci",
        "authority":"local_player_control_not_canonical_world_edit",
    }
    return capture,dash,receipt,dispatch


class NativeWindDashAuditTests(unittest.TestCase):
    def test_genuine_approved_impulse_changes_actual_solved_velocity(self):
        c,d,a,b=fixture()
        result=verify_native_wind_dash_playthrough(c,d,a,b,fps=60)
        self.assertEqual(result["peak_added_velocity_along_impulse_mps"],3)
        self.assertEqual(result["approved_skill_level"],2)
        self.assertEqual(result["activation_tick"],2)
        self.assertEqual(len(result["receipt_digest"]),64)
        self.assertEqual(result,verify_native_wind_dash_playthrough(c,d,a,b,fps=60))

    def test_explicit_playthrough_budget_is_checked(self):
        c,d,a,b=fixture()
        self.assertEqual(verify_native_wind_dash_playthrough(
            c,d,a,b,fps=60,expected_frames=5)["frame_count"],5)
        for bad in (4,6,129,True):
            with self.subTest(expected=bad),self.assertRaises(NativeQuestSessionError):
                verify_native_wind_dash_playthrough(
                    c,d,a,b,fps=60,expected_frames=bad)

    def test_physics_mass_cannot_mutate_during_comparison(self):
        for side in ("control","dash"):
            c,d,a,b=fixture()
            target=c if side=="control" else d
            target[3]["actors"][0]["physics_body"]["mass_kg"]=2.5
            with self.subTest(side=side),self.assertRaises(NativeQuestSessionError):
                verify_native_wind_dash_playthrough(c,d,a,b,fps=60)

    def test_no_visible_physics_change_rejected(self):
        c,d,a,b=fixture()
        with self.assertRaisesRegex(NativeQuestSessionError,"did not measurably change"):
            verify_native_wind_dash_playthrough(c,c,a,b,fps=60)

    def test_locked_or_incorrect_ability_rejected(self):
        for kind,expected in (
            ("expected_unlocked_skills",{}),
            ("expected_local_level",1),
            ("receipt_digest","f"*64),
        ):
            c,d,a,b=fixture()
            b[kind]=expected
            with self.subTest(kind=kind),self.assertRaises(NativeQuestSessionError):
                verify_native_wind_dash_playthrough(c,d,a,b,fps=60)

    def test_tampered_actor_impulse_source_or_mass_rejected(self):
        for kind,value in (
            ("scene_candidate_digest","a"*64),
            ("input_mode","human_key_G"),
            ("source_game_tick",3),
            ("impulse_world_xyz_ns",[200,0,0]),
            ("bounded_impulse_ns",45),
            ("player_mass_kg",3),
            ("velocity_before_world_xyz_mps",[1,0,0]),
            ("approved_dispatch_digest","0"*64),
            ("skill_required_level",3),
        ):
            c,d,a,b=fixture()
            a[kind]=value
            with self.subTest(kind=kind),self.assertRaises(NativeQuestSessionError):
                verify_native_wind_dash_playthrough(c,d,a,b,fps=60)

    def test_source_before_ability_and_missing_ticks_rejected(self):
        for kind in ("pre_velocity","pre_position","missing_tick","wrong_fps","truncated"):
            c,d,a,b=fixture()
            if kind=="pre_velocity":
                d[1]["actors"][0]["velocity_xyz_mps"]=[3,0,0]
            elif kind=="pre_position":
                d[0]["actors"][0]["world_xyz_m"]=[30,0,0]
            elif kind=="missing_tick":
                d[3]["native_tick"]=100
            elif kind=="wrong_fps":
                d[2]["fps"]=50
            elif kind=="truncated":
                d.pop()
            with self.subTest(kind=kind),self.assertRaises(NativeQuestSessionError):
                verify_native_wind_dash_playthrough(c,d,a,b,fps=60)

    def test_nonfinite_values_and_unapproved_body_rejected(self):
        for kind in ("nan","duplicate_actor","fake_body"):
            c,d,a,b=fixture()
            if kind=="nan":
                d[3]["actors"][0]["velocity_xyz_mps"]=[float("nan"),0,0]
            elif kind=="duplicate_actor":
                d[1]["actors"].append(deepcopy(d[1]["actors"][0]))
            else:
                d[2]["actors"][0]["physics_body"]["mode"]="static"
            with self.subTest(kind=kind),self.assertRaises(NativeQuestSessionError):
                verify_native_wind_dash_playthrough(c,d,a,b,fps=60)
