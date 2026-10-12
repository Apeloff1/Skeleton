"""Source-bound moving-pair CCD, angular impulses and radial cable regressions."""
from __future__ import annotations

from copy import deepcopy
from math import isqrt
import unittest

from skeleton.ai.game_builder.advanced_physics_runtime import (
    ACTIONS, default_layout, PhysicsActionError,
)
from skeleton.ai.game_builder.advanced_physics_dynamics import (
    _contact_time, resolve_moving_pairs, solve_radial_rope,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editors import make_editor_document
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame, import_advanced_savegame,
)


class PhysicsDynamicsTests(unittest.TestCase):
    @staticmethod
    def cfg(**settings):
        return make_editor_document("physics", settings)["settings"]

    @classmethod
    def scenario(cls, settings=None, *, seed=0, transform=None):
        config=cls.cfg(**(settings or {}))
        layout=default_layout(config, seed)
        if transform:
            transform(layout)
        return make_advanced_scene("physics", settings, seed=seed, layout=layout)

    @staticmethod
    def crossing(layout):
        layout["bodies"][0]["position"]=[250, 900, 0]
        layout["bodies"][0]["velocity"]=[260, 0, 0]
        layout["bodies"][0]["break_threshold"]=1000
        layout["bodies"][1]["position"]=[600, 900, 0]
        layout["bodies"][1]["velocity"]=[-260, 0, 0]
        layout["bodies"][1]["break_threshold"]=1000

    def test_swept_static_barrier_handles_exit_time_beyond_frame(self):
        cfg={"speed_limit":400,"impulse_strength":500,"air_drag":0,"gravity":0}
        def layout_modify(layout):
            layout["fixtures"]=[{"position":[430,900,0],
                                "half_size":[10,100,40],"layer":3}]
        scene=self.scenario(cfg,transform=layout_modify)
        played=run_advanced_session("physics",cfg,
                                    ("push:east","push:east"),scene=scene)
        self.assertTrue(verify_advanced_session(played,cfg))
        self.assertTrue(any("swept_fixture_contact" in row["events"]
                            for row in played["trace"]))
        self.assertLess(played["state"]["bodies"][0]["position"][0],430)

    def test_two_fast_opposing_objects_cannot_pass_through_each_other(self):
        cfg={"speed_limit":350,"gravity":0,"air_drag":0}
        scene=self.scenario(cfg,transform=self.crossing)
        r=run_advanced_session("physics",cfg,("inspect",),scene=scene)
        self.assertTrue(verify_advanced_session(r,cfg))
        self.assertEqual(r["state"]["continuous_pair_contacts"],1)
        a,b=r["state"]["bodies"]
        self.assertLess(a["position"][0],b["position"][0])
        self.assertTrue(any("continuous_pair_time_of_impact" in row["events"]
                            for row in r["trace"]))
        self.assertLess(a["velocity"][0],260)
        self.assertGreater(b["velocity"][0],-260)

    def test_explicit_discrete_policy_does_not_fabricate_ccd(self):
        cfg={"speed_limit":350,"gravity":0,"air_drag":0,
             "continuous_pair_collision":False}
        scene=self.scenario(cfg,transform=self.crossing)
        r=run_advanced_session("physics",cfg,("inspect",),scene=scene)
        self.assertEqual(r["state"]["continuous_pair_contacts"],0)
        self.assertTrue(verify_advanced_session(r,cfg))

    def test_masked_out_contacts_do_not_transfer_energy_or_spin(self):
        cfg={"speed_limit":350,"gravity":0,"air_drag":0}
        def layout_modify(layout):
            self.crossing(layout)
            layout["bodies"][1]["mask"]=2
        scene=self.scenario(cfg,transform=layout_modify)
        r=run_advanced_session("physics",cfg,("inspect",),scene=scene)
        self.assertEqual(r["state"]["continuous_pair_contacts"],0)
        self.assertEqual(r["state"]["bodies"][0]["angular_velocity"],0)
        self.assertTrue(verify_advanced_session(r,cfg))

    def test_parallel_flights_with_separated_y_are_not_collisions(self):
        cfg={"speed_limit":350,"gravity":0,"air_drag":0}
        def layout_modify(layout):
            self.crossing(layout)
            layout["bodies"][1]["position"][1]=700
        scene=self.scenario(cfg,transform=layout_modify)
        r=run_advanced_session("physics",cfg,("inspect",),scene=scene)
        self.assertEqual(r["state"]["continuous_pair_contacts"],0)

    def test_true_3d_depth_can_prevent_a_2d_projected_collision(self):
        cfg={"dimension":"3d","speed_limit":350,"gravity":0,"air_drag":0}
        def layout_modify(layout):
            self.crossing(layout)
            layout["bodies"][0]["position"][2]=60
            layout["bodies"][1]["position"][2]=240
        scene=self.scenario(cfg,transform=layout_modify)
        r=run_advanced_session("physics",cfg,("inspect",),scene=scene)
        self.assertEqual(r["state"]["continuous_pair_contacts"],0)
        self.assertTrue(verify_advanced_session(r,cfg))

    def test_angular_impulse_consumes_budget_and_rotates_original_body(self):
        cfg={"gravity":0,"angular_damping":0,"torque_strength":800,
             "impulse_budget":2}
        played=run_advanced_session("physics",cfg,
                                    ("torque:cw","inspect","torque:ccw"))
        self.assertTrue(verify_advanced_session(played,cfg))
        body=played["state"]["bodies"][0]
        self.assertGreater(body["orientation"],0)
        self.assertEqual(played["state"]["impulses_left"],0)
        self.assertIn("finite_angular_impulse_applied",played["trace"][0]["events"])
        with self.assertRaises(AdvancedRuntimeError):
            run_advanced_session("physics",cfg,
                ("torque:cw","torque:ccw","torque:cw"))

    def test_brake_actually_slows_angular_velocity(self):
        cfg={"gravity":0,"angular_damping":0,"torque_strength":1000}
        spin=run_advanced_session("physics",cfg,("torque:cw",))["state"]["bodies"][0]
        braked=run_advanced_session("physics",cfg,
                ("torque:cw","brake"))["state"]["bodies"][0]
        self.assertLess(abs(braked["angular_velocity"]),abs(spin["angular_velocity"]))

    def test_off_center_dynamic_contact_transfers_real_spin(self):
        cfg={"speed_limit":350,"gravity":0,"air_drag":0,
             "spin_transfer":100,"angular_damping":0}
        def offset(layout):
            self.crossing(layout)
            layout["bodies"][1]["position"][1]=950
        scene=self.scenario(cfg,transform=offset)
        r=run_advanced_session("physics",cfg,("inspect",),scene=scene)
        self.assertEqual(r["state"]["continuous_pair_contacts"],1)
        self.assertNotEqual(r["state"]["bodies"][0]["angular_velocity"],0)

    def test_radial_cable_uses_euclidean_length_and_preserves_substance(self):
        cfg={"gravity":0,"rope_length":350,"rope_strength":200}
        r=run_advanced_session("physics",cfg,("attach:0",))
        body=r["state"]["bodies"][0]
        anchor=r["state"]["anchors"][0]
        dist=isqrt(sum((body["position"][axis]-anchor[axis])**2
                       for axis in range(2)))
        self.assertLessEqual(dist,351)
        self.assertGreater(r["state"]["peak_cable_extension"],0)
        self.assertIsNotNone(r["state"]["rope"])
        self.assertTrue(verify_advanced_session(r,cfg))

    def test_overstretched_cable_snaps_instead_of_teleporting_payload(self):
        cfg={"gravity":0,"rope_length":300,"rope_strength":1}
        r=run_advanced_session("physics",cfg,("attach:0",))
        self.assertIsNone(r["state"]["rope"])
        self.assertEqual(r["state"]["rope_breaks"],1)
        self.assertIn("physical_cable_snapped",r["state"]["events"])

    def test_replay_and_save_include_rotation_and_contact_history(self):
        cfg={"gravity":0,"angular_damping":0}
        original=run_advanced_session("physics",cfg,("torque:cw","step:4"))
        record=export_advanced_savegame(original,cfg)
        self.assertEqual(import_advanced_savegame(record)["session"],original)
        forged=deepcopy(original)
        forged["state"]["bodies"][0]["orientation"] += 1
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged,cfg)
        forged=deepcopy(original)
        forged["state"]["continuous_pair_contacts"]=999
        with self.assertRaises(AdvancedRuntimeError):
            verify_advanced_session(forged,cfg)

    def test_all_angular_controls_are_bounded_and_documented(self):
        schema=self.cfg()
        for key in ("torque_strength","spin_transfer","max_angular_speed",
                    "angular_damping","continuous_pair_collision",
                    "material_restitution"):
            self.assertIn(key,schema)
        self.assertIn("torque:cw",ACTIONS)
        self.assertIn("torque:ccw",ACTIONS)
        self.assertEqual(len(ACTIONS),len(set(ACTIONS)))

    def test_legacy_untrusted_layout_cannot_add_fake_rotational_state(self):
        layout=default_layout(self.cfg(),0)
        layout["bodies"][0]["orientation"]=359999
        with self.assertRaises(SceneError):
            make_advanced_scene("physics",layout=layout)
        layout=default_layout(self.cfg(),0)
        layout["bodies"][0]["angular_velocity"]=10000
        with self.assertRaises(SceneError):
            make_advanced_scene("physics",layout=layout)


if __name__=="__main__":
    unittest.main()
