"""Full advanced-physics scene integration, continuous collision and independent audits."""
import unittest
from dataclasses import replace

from skeleton.jeeves.game_frontier_advanced_physics import (
    RigidBody,AeroProfile,WakeSource,UpdraftColumn,TractionSurface,
    Climber,CollisionContact,sweep_spheres,sweep_sphere_plane,
    resolve_contact,AdvancedPhysicsError,
)
from skeleton.jeeves.game_frontier_production import (
    Vec3, Bone, BonePose, CharacterSkeleton, AnimationClip,
    AnimationKeyframe, Percept,
)
from skeleton.jeeves.game_frontier_dynamics import (
    WorldAxis, WindField, WindLayer, WindVector,
)
from skeleton.jeeves.game_frontier_ecosystem import (
    AirConditions, LiquidGrid,
)
from skeleton.jeeves.game_frontier_realism import (
    audit_scene_realism, RealismAuditError,
)
from skeleton.jeeves.game_frontier import compile_frontier_scene


A = "a"*64


def scene_params() -> dict:
    pose=BonePose(Vec3(0,0,0))
    return dict(
        world_axes=WorldAxis(1,.6,.6,.5,.6,.1,.3),
        cell_x=0,cell_y=0,
        wind_field=WindField((WindLayer(0,WindVector(8,0)),)),
        clouds=(),time_s=1,delta_s=.05,
        skeleton=CharacterSkeleton((
            Bone("root",-1,Vec3(0,0,0),Vec3(0,0,1),.2),)),
        animation=AnimationClip("idle",(
            AnimationKeyframe(0,(pose,)),
            AnimationKeyframe(1000,(pose,)),
        )),
        animation_time_ms=500,
        era="early_3d",fps=60,
        evidence=(Percept("hero","character",True,1,.8,A),),
        world_goal_kind="character",
        available_actions=("inspect","interact"),
        air_conditions=AirConditions(altitude_m=830,temperature_c=20),
        advanced_body=RigidBody(
            "hero",Vec3(0,0,30),Vec3(0,0,-20),85,.5,
            restitution=.15,friction=.8),
        advanced_aero=AeroProfile(1.,.75),
        advanced_traction=TractionSurface(
            Vec3(0,0,1),.8,.65,wetness=.4,ice_fraction=.15),
        advanced_climber=Climber(85,900,.75,.9,.8,load_kg=8),
        advanced_wakes=(WakeSource("cliff",Vec3(-4,0,28),2,.4,40),),
        advanced_thermals=(UpdraftColumn(Vec3(0,0,0),20,5,80),),
        advanced_turbulence_amplitude=.5,
        liquid_grid=LiquidGrid(2,1,1,(0,0),(1,0)),
    )


class AdvancedSceneTests(unittest.TestCase):
    def test_advanced_scene_is_coherent_and_auditable(self):
        config=scene_params()
        first=compile_frontier_scene(**config)
        second=compile_frontier_scene(**config)
        self.assertEqual(first.manifest_digest,second.manifest_digest)
        self.assertFalse(first.approved_for_runtime)
        info=first.manifest["advanced_physics"]
        self.assertEqual(info["body"]["mass_kg"],85)
        self.assertGreater(info["terminal_velocity_mps"],0)
        self.assertGreater(info["updraft_mps"],0)
        self.assertGreater(info["traction"]["available_force_n"],0)
        self.assertEqual(info["authority"],"candidate_only_no_native_mutation")
        report=first.manifest["realism_audit"]
        self.assertIn("aerodynamics",report["participating_domains"])
        self.assertIn("climbing",report["participating_domains"])
        self.assertIn("atmosphere",report["participating_domains"])
        self.assertIn("liquid",report["participating_domains"])
        self.assertTrue(report["reference_checks_passed"])
        self.assertEqual(len(report["evidence_digest"]),64)

    def test_advanced_collision_has_weight_impulse_and_energy_receipts(self):
        cfg=scene_params()
        cfg.update(
            advanced_body=RigidBody("A",Vec3(0,0,3),Vec3(10,0,0),40,.5,
                                    restitution=.2,friction=.7),
            advanced_other_body=RigidBody("B",Vec3(1,0,3),Vec3(-2,0,0),110,.5,
                                          restitution=.2,friction=.7),
            advanced_contact=CollisionContact(
                Vec3(.5,0,3),Vec3(1,0,0),.03),
        )
        scene=compile_frontier_scene(**cfg)
        impact=scene.manifest["advanced_physics"]["impact"]
        self.assertGreater(impact["impulse_ns"],0)
        self.assertLess(impact["momentum_residual_ns"],1e-7)
        self.assertTrue(scene.manifest["realism_audit"]["reference_checks_passed"])

    def test_non_opt_in_keeps_earlier_scene_behavior(self):
        cfg=scene_params()
        for key in (
            "advanced_body","advanced_aero","advanced_traction",
            "advanced_climber","advanced_wakes","advanced_thermals",
            "advanced_turbulence_amplitude",
        ):
            cfg.pop(key)
        scene=compile_frontier_scene(**cfg)
        self.assertIsNone(scene.manifest["advanced_physics"])
        self.assertNotIn("aerodynamics",
                         scene.manifest["realism_audit"]["participating_domains"])
        self.assertFalse(scene.approved_for_runtime)

    def test_partial_advanced_schema_fails_closed(self):
        cfg=scene_params()
        cfg.pop("advanced_climber")
        with self.assertRaises(ValueError):
            compile_frontier_scene(**cfg)
        cfg=scene_params()
        cfg.pop("advanced_body")
        with self.assertRaises(ValueError):
            compile_frontier_scene(**cfg)

    def test_audit_detects_bad_mass_conservation(self):
        cfg=scene_params()
        scene=compile_frontier_scene(**cfg)
        altered=dict(scene.manifest)
        liquid=dict(altered["liquid"])
        liquid["mass_residual_m3"]=25
        altered["liquid"]=liquid
        report=audit_scene_realism(altered)
        self.assertFalse(report.reference_checks_passed)
        self.assertTrue(any(v.domain=="liquid" and v.check=="mass_conserved"
                            and not v.passed for v in report.invariants))

    def test_covers_advancing_time_substeps(self):
        cfg=scene_params()
        cfg["delta_s"]=2
        cfg.pop("liquid_grid")
        first=compile_frontier_scene(**cfg)
        self.assertGreater(first.manifest["advanced_physics"]["terminal_velocity_mps"],0)
        self.assertEqual(first.manifest["render"]["fps"],60)


class ContinuousCollisionTests(unittest.TestCase):
    def test_two_fast_spheres_do_not_tunnel(self):
        a=RigidBody("A",Vec3(-10,0,0),Vec3(1000,0,0),20,.5)
        b=RigidBody("B",Vec3(10,0,0),Vec3(-1000,0,0),20,.5)
        impact=sweep_spheres(a,b,delta_s=.02)
        self.assertIsNotNone(impact)
        self.assertAlmostEqual(impact.time_of_impact_s,.0095,places=6)
        self.assertEqual(impact.source,"sphere_sphere_linear_ccd")
        self.assertAlmostEqual(impact.contact.normal_a_to_b.x,1)

    def test_separating_spheres_do_not_collide(self):
        a=RigidBody("A",Vec3(-4,0,0),Vec3(-10,0,0),10,.5)
        b=RigidBody("B",Vec3(4,0,0),Vec3(10,0,0),10,.5)
        self.assertIsNone(sweep_spheres(a,b,delta_s=1))

    def test_plane_sweep_hits_fast_character(self):
        a=RigidBody("fall",Vec3(0,0,5),Vec3(0,0,-1000),70,.5,
                    restitution=0)
        impact=sweep_sphere_plane(
            a,plane_point=Vec3(0,0,0),
            plane_outward_normal=Vec3(0,0,1),delta_s=.01)
        self.assertIsNotNone(impact)
        self.assertAlmostEqual(impact.time_of_impact_s,.0045,places=6)
        self.assertEqual(impact.contact.normal_a_to_b,Vec3(0,0,-1))
        at_touch=replace(a,position=a.position+
                         a.velocity.scaled(impact.time_of_impact_s))
        settled=resolve_contact(at_touch,None,impact.contact)
        self.assertAlmostEqual(settled.body_a.velocity.z,0,places=5)

    def test_ccd_rejects_invalid_time_and_plane(self):
        a=RigidBody("sphere",Vec3(0,0,3),Vec3(0,0,-4),5,.5)
        with self.assertRaises(AdvancedPhysicsError):
            sweep_sphere_plane(a,plane_point=Vec3(0,0,0),
                               plane_outward_normal=Vec3(0,0,2),delta_s=1)
        with self.assertRaises(AdvancedPhysicsError):
            sweep_spheres(a,a,delta_s=-1)


if __name__=="__main__":
    unittest.main()
