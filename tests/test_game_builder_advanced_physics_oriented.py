"""Deterministic oriented-box SAT contacts, original shape authoring and replay."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.advanced_physics_oriented import (
    sin_cos, box_vertices, sat_manifold,
)
from skeleton.ai.game_builder.advanced_physics_runtime import default_layout
from skeleton.ai.game_builder.system_editors import make_editor_document
from skeleton.ai.game_builder.advanced_level_scenes import (
    SceneError, make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_gameplay_save import (
    export_advanced_savegame, import_advanced_savegame,
)


class OriginalOrientedContactTests(unittest.TestCase):
    @staticmethod
    def cfg(**overrides):
        return make_editor_document("physics", overrides)["settings"]

    @classmethod
    def scene(cls, options=None, transform=None):
        config=cls.cfg(**(options or {}))
        chart=default_layout(config,0)
        if transform:
            transform(chart)
        return make_advanced_scene("physics",options,layout=chart)

    @staticmethod
    def shape(x,y,hx,hy,angle=0,z=0):
        return {"position":[x,y,z],"half_size":[hx,hy],"orientation":angle}

    def test_right_angle_lookup_is_deterministic_and_orthogonal(self):
        self.assertEqual(sin_cos(0),(0,10000))
        self.assertEqual(sin_cos(90000),(10000,0))
        self.assertEqual(sin_cos(180000),(0,-10000))
        self.assertEqual(sin_cos(270000),(-10000,0))
        self.assertEqual(sin_cos(360000),sin_cos(0))

    def test_rotating_original_rectangle_changes_real_sat_result(self):
        horizontal=self.shape(300,600,40,10)
        neighbor=self.shape(300,645,40,10)
        self.assertIsNone(sat_manifold(horizontal,neighbor))
        horizontal["orientation"]=90000
        contact=sat_manifold(horizontal,neighbor)
        self.assertIsNotNone(contact)
        self.assertGreater(contact["depth"],0)
        self.assertEqual(len(contact["normal"]),2)
        self.assertEqual(len(contact["point"]),2)

    def test_separating_axis_catches_false_aabb_overlap(self):
        slender=self.shape(200,300,40,10)
        separated=self.shape(200,330,40,10)
        self.assertIsNone(sat_manifold(slender,separated))
        self.assertLess(abs(300-330),40+40)  # Legacy square would overlap.
        self.assertEqual(len(box_vertices(slender["position"],
                                           slender["half_size"],0)),4)

    def test_source_allows_non_square_bodies_only_in_real_sat_mode(self):
        policy={"collision_geometry":"oriented_box","gravity":0}
        def chart_edit(chart):
            chart["bodies"][0]["position"]=[200,600,0]
            chart["bodies"][0]["shape_half"]=[40,10]
            chart["bodies"][1]["position"]=[200,630,0]
            chart["bodies"][1]["shape_half"]=[40,10]
        scene=self.scene(policy,chart_edit)
        self.assertEqual(scene,validate_advanced_scene(scene,policy))
        r=run_advanced_session("physics",policy,("inspect",),scene=scene)
        self.assertEqual(r["state"]["oriented_contacts"],0)
        self.assertTrue(verify_advanced_session(r,policy))
        with self.assertRaises(SceneError):
            self.scene({"collision_geometry":"aabb","gravity":0},chart_edit)

    def test_rotated_authored_shape_overlap_is_rejected_not_trusted(self):
        policy={"collision_geometry":"oriented_box","gravity":0}
        def collide(chart):
            chart["bodies"][0]["position"]=[300,600,0]
            chart["bodies"][0]["shape_half"]=[40,10]
            chart["bodies"][0]["initial_orientation"]=90000
            chart["bodies"][1]["position"]=[300,645,0]
            chart["bodies"][1]["shape_half"]=[40,10]
        with self.assertRaises(SceneError):
            self.scene(policy,collide)

    def test_real_torque_rotates_and_causes_contact_not_only_visualization(self):
        policy={"collision_geometry":"oriented_box","gravity":0,
                "air_drag":0,"angular_damping":0,
                "torque_strength":2000,"max_angular_speed":20000}
        def original(chart):
            chart["bodies"][0]["position"]=[300,600,0]
            chart["bodies"][0]["shape_half"]=[40,10]
            chart["bodies"][1]["position"]=[300,642,0]
            chart["bodies"][1]["shape_half"]=[40,10]
        scene=self.scene(policy,original)
        result=run_advanced_session(
            "physics",policy,("torque:cw",)+("step:4",)*5,scene=scene)
        self.assertGreater(result["state"]["bodies"][0]["orientation"],0)
        self.assertGreater(result["state"]["oriented_contacts"],0)
        self.assertTrue(any(
            ("oriented_dynamic_manifold_resolved" in item["events"] or
             "oriented_rotating_swept_dynamic_manifold_resolved" in item["events"])
            for item in result["trace"]))
        self.assertTrue(verify_advanced_session(result,policy))

    def test_oriented_fixture_rotation_is_bound_to_original_source(self):
        cfg={"collision_geometry":"oriented_box","gravity":0}
        scene=self.scene(cfg)
        changed=deepcopy(scene)
        changed["layout"]["fixtures"][0]["orientation"]=90000
        with self.assertRaises(SceneError):
            validate_advanced_scene(changed,cfg)
        # Source owner may construct a *new* signed level with the change.
        updated=self.scene(cfg,lambda layout:
                           layout["fixtures"][0].update(orientation=90000))
        self.assertNotEqual(updated["digest"],scene["digest"])
        self.assertTrue(verify_advanced_session(
            run_advanced_session("physics",cfg,("inspect",),scene=updated),cfg))

    def test_authoritative_manifold_has_contact_normal_and_bounded_history(self):
        cfg={"collision_geometry":"oriented_box","gravity":0,
             "torque_strength":2000,"angular_damping":0}
        def chart_edit(chart):
            chart["bodies"][0]["position"]=[300,600,0]
            chart["bodies"][0]["shape_half"]=[40,10]
            chart["bodies"][1]["position"]=[300,642,0]
            chart["bodies"][1]["shape_half"]=[40,10]
        scene=self.scene(cfg,chart_edit)
        r=run_advanced_session("physics",cfg,
             ("torque:cw",)+("step:4",)*8,scene=scene)
        self.assertLessEqual(len(r["state"]["contact_manifolds"]),16)
        self.assertTrue(all(set(m)=={"frame","kind","normal","penetration","point"}
                            for m in r["state"]["contact_manifolds"]))
        self.assertTrue(all(m["penetration"]>0 for m in
                            r["state"]["contact_manifolds"]))

    def test_invalid_authored_rotations_and_shapes_are_denied(self):
        cfg={"collision_geometry":"oriented_box"}
        for mutate in (
            lambda l:l["bodies"][0].update(shape_half=[40,-5]),
            lambda l:l["bodies"][0].update(initial_orientation=True),
            lambda l:l["bodies"][0].update(initial_orientation=360000),
            lambda l:l["bodies"][0].update(shape_half=[200,5]),
            lambda l:l["fixtures"][0].update(orientation=-4),
            lambda l:l["fixtures"][0].update(script="shatter all"),
        ):
            chart=default_layout(self.cfg(**cfg),0)
            mutate(chart)
            with self.assertRaises(SceneError):
                make_advanced_scene("physics",cfg,layout=chart)

    def test_3d_extruded_oriented_boxes_respect_real_depth_separation(self):
        a=self.shape(300,600,40,10,90000,z=50)
        b=self.shape(300,625,40,10,0,z=160)
        a["z_radius"]=40;b["z_radius"]=40
        self.assertIsNone(sat_manifold(a,b))
        b["position"][2]=80
        self.assertIsNotNone(sat_manifold(a,b))

    def test_replay_rejects_forged_contact_point_and_earned_victory(self):
        cfg={"collision_geometry":"oriented_box","gravity":0}
        r=run_advanced_session("physics",cfg,("inspect","torque:cw"))
        self.assertTrue(verify_advanced_session(r,cfg))
        for key,val in (("oriented_contacts",999),("finished",True)):
            fake=deepcopy(r);fake["state"][key]=val
            with self.assertRaises(AdvancedRuntimeError):
                verify_advanced_session(fake,cfg)
        save=export_advanced_savegame(r,cfg)
        self.assertEqual(import_advanced_savegame(save)["session"],r)

    def test_legacy_aabb_mode_preserves_trusted_original_reference(self):
        original=run_advanced_session("physics",actions=("push:east","step:4"))
        self.assertEqual(original["state"]["oriented_contacts"],0)
        self.assertTrue(verify_advanced_session(original))


if __name__=="__main__":
    unittest.main()
